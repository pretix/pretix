import datetime
import operator
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from itertools import chain
from typing import (
    TYPE_CHECKING, Any, Callable, ClassVar, Dict, Final, List, Literal,
    Optional, Protocol, Set, Tuple, TypeAlias,
)

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Prefetch, QuerySet
from django.utils.timezone import make_aware
from django.utils.translation import gettext_lazy as _
from django_stubs_ext import StrOrPromise

from pretix.base.decimal import round_decimal
from pretix.base.models import Event, Item, ItemVariation, Order, OrderPosition
from pretix.base.reldate import ModelRelativeDateTimeField, RelativeDateWrapper
from pretix.base.signals import self_service_cancellation_checks
from pretix.helpers import ensure_no_queries

"""
Supporting self-service cancellation requires us to do two main things:
1. uphold the business logic of pretix and the installed plugins
2. charge the customer the appropriate fees for their cancellation

Number 1 is a question of bringing enough checks into place and prevent a
cancellation if one of them is violated.
Checks need to subclass `CancellationCheck` and can be provided via the new
`self_service_cancellation_checks` signal.

Number 2 is trickier because organizers will have complex^(TM) cancellation
fee structures and expressing these in an understandable way is a challenge.
Especially when taking support cases into consideration that have to debug
certain behaviour long after.
The cancellation fees are computed via `CancellationRules`.

When a customer triggers a self service cancellation, we will:
1. Positions
    a. Evaluate all `CancellationChecks` that are concerned with individual positions
    b. Evaluate all `CancellationRules` that are concerned with individual positions and compute the fees
    c. Choose for each position the cheapest `CancellationRules` position result available
2. Process
    a. Evaluate all `CancellationChecks` that are concerned with the process of cancellation
    b. Evaluate all `CancellationRules` that are concerned with the process of cancellation
    c. Choose the cheapest `CancellationRules` process result available
3. Return all results for Checks and Rules

Step 1c. and 2c. are kept separate intentionally.
The alternative of finding the cheapest cancellation option overall (process and position) would
require us to check the full combinatorics of possible process and position fees, resulting
in unfeasible runtime behaviour, and if we would optimize it in difficult to explain non-optimal
situations.
"""


class FeeType(models.TextChoices):
    """
    Process fees can be added on top of all position fees, or they
    can set a floor for the minimum cancellation fee that this will incur.
    """
    MINIMUM = "min_process_fee", _("Minimum total fee")
    ADDITIONAL = "add_process_fee", _("Additional fee")
    POSITION = "position_fee", _("Position fee")


class CheckTypes(models.TextChoices):
    POSITION = "position", _("Order Position Cancellation Rule")
    PROCESS = "process", _("Cancellation Process Rule")


@dataclass(frozen=True)
class CheckResult:
    """
    Result of an individual cancellation check.
    The check result only encodes if the check allows or disallows cancellation via
    `cancellation_possible`
    """
    id: str
    reason: StrOrPromise
    cancellation_possible: bool
    type: Literal['check'] = field(default="check")

    @classmethod
    def from_dict(cls, data: dict) -> "CheckResult":
        return cls(**data)


@dataclass(frozen=True)
class RuleResult:
    """
    Result of evaluating a CancellationRule.
    A rule can consist out of multiple different checks, each partial_result is recorded individually.

    A RuleResult encodes both the feasibility of a cancellation via `cancellation_possible` and
    the resulting consequences in form of fees which can be expressed as:
    - absolute position fees of a fixed amount
    - relative position fees of a percentage of the position price
    - minimum process fees, the total cancellation fee across all positions and the process must be at least this
    - additional process fee, an additional processing fee is charged in addition to the per position fees
    """
    id: int
    partial_results: List[CheckResult]
    fee_type: FeeType
    fee: Decimal

    type: Literal['rule'] = field(default="rule")

    @classmethod
    def from_dict(cls, data: dict) -> "RuleResult":
        return cls(
            id=data["id"],
            partial_results=[CheckResult.from_dict(r) for r in data["partial_results"]],
            fee_type=FeeType(data["fee_type"]),
            fee=Decimal(data["fee"]),
        )

    @property
    def cancellation_possible(self) -> bool:
        return all(result.cancellation_possible for result in self.partial_results)

    @classmethod
    def from_absolute_fee(
            cls,
            id: int,
            partial_results: List[CheckResult],
            fee_type: Literal[FeeType.POSITION],
            absolute_fee: Decimal
    ) -> "RuleResult":
        return RuleResult(id=id, partial_results=partial_results, fee_type=fee_type, fee=absolute_fee)

    @classmethod
    def from_relative_fee(
            cls,
            id: int,
            partial_results: List[CheckResult],
            fee_type: Literal[FeeType.POSITION],
            position_price: Decimal,
            percentage: Decimal,
            currency: str
    ) -> "RuleResult":
        return RuleResult(id=id, partial_results=partial_results, fee_type=fee_type,
                          fee=round_decimal(position_price * (percentage / 100), currency))

    @classmethod
    def from_process_fee(
            cls,
            id: int,
            partial_results: List[CheckResult],
            fee_type: Literal[FeeType.MINIMUM, FeeType.ADDITIONAL],
            absolute_fee: Decimal,
            reference_price: Decimal
    ) -> "RuleResult":
        if fee_type == FeeType.MINIMUM:
            if reference_price < absolute_fee:
                fee = absolute_fee - reference_price
            else:
                fee = Decimal(0)
        elif fee_type == FeeType.ADDITIONAL:
            fee = absolute_fee
        else:
            raise ValueError("Unknown fee type")

        return RuleResult(id=id, partial_results=partial_results, fee_type=fee_type, fee=fee)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, RuleResult):
            return NotImplemented

        if self.cancellation_possible == other.cancellation_possible:
            return self.fee < other.fee
        else:
            return self.cancellation_possible and not other.cancellation_possible


@dataclass(frozen=True)
class Checks:
    position: List["CancellationCheck"]
    process: List["CancellationCheck"]

    @property
    def prefetches(self) -> List[Callable[[], Prefetch]]:
        return list(chain.from_iterable(
            check.prefetches for check in [*self.position, *self.process]
        ))

    @property
    def related_selects(self) -> List[str]:
        return list(chain.from_iterable(
            check.related_selects for check in [*self.position, *self.process]
        ))


PositionSet: TypeAlias = Set[OrderPosition]


class PositionCheckFn(Protocol):
    def __call__(self, order: Order, keep: PositionSet, position: OrderPosition, check_ts: datetime.datetime,
                 /) -> Optional[CheckResult]:
        ...


class ProcessCheckFn(Protocol):
    def __call__(self, order: Order, keep: PositionSet, check_ts: datetime.datetime, /) -> Optional[CheckResult]:
        ...


@dataclass(frozen=True)
class CancellationCheck:
    id: str
    type: CheckTypes
    check_fn: PositionCheckFn | ProcessCheckFn = field(compare=False)
    prefetches: List[Callable[[], Prefetch]] = field(default_factory=list)
    related_selects: List[str] = field(default_factory=list)

    def evaluate(self, order: Order, keep: PositionSet,
                 position: OrderPosition | None, check_ts: datetime.datetime) -> Optional[CheckResult]:
        if position and self.type == CheckTypes.POSITION:
            return self.check_fn(order, keep, position, check_ts)
        elif position is None and self.type == CheckTypes.PROCESS:
            return self.check_fn(order, keep, check_ts)
        else:
            raise ValidationError("Type of the rule doesn't match the check_fn")


@dataclass(frozen=True)
class PositionResult:
    position_check_results: Dict[int, List[CheckResult]]
    position_rule_results: Dict[int, List[RuleResult]]

    @classmethod
    def from_dict(cls, data: dict) -> "PositionResult":
        return cls(
            position_check_results={
                int(pos_id): [CheckResult.from_dict(r) for r in results]
                for pos_id, results in data["position_check_results"].items()
            },
            position_rule_results={
                int(pos_id): [RuleResult.from_dict(r) for r in results]
                for pos_id, results in data["position_rule_results"].items()
            },
        )

    @property
    def cancellation_possible(self) -> bool:
        def ok(results: List[CheckResult] | List[RuleResult]) -> bool:
            return all([val.cancellation_possible for val in results]) if results else True

        return all(
            ok(results)
            for d in
            (self.position_check_results,
             {key: [min(pos_res)] for key, pos_res in self.position_rule_results.items() if pos_res})
            for results in d.values()
        )

    @property
    def fee_value(self) -> Decimal:
        fee_value = Decimal("0.00")
        for pos_id, results in self.position_rule_results.items():
            if len(results) > 0:
                best_option = min(results)
                if best_option.cancellation_possible:
                    fee_value += best_option.fee
        return fee_value


@dataclass(frozen=True)
class ProcessResult:
    process_check_results: List[CheckResult]
    process_rule_results: List[RuleResult]

    @classmethod
    def from_dict(cls, data: dict) -> "ProcessResult":
        return cls(
            process_check_results=[CheckResult.from_dict(r) for r in data["process_check_results"]],
            process_rule_results=[RuleResult.from_dict(r) for r in data["process_rule_results"]],
        )

    @property
    def cancellation_possible(self) -> bool:
        results: List[CheckResult | RuleResult] = [*self.process_check_results]
        if self.process_rule_results:
            results.append(min(self.process_rule_results))
        return all(res.cancellation_possible for res in results)

    @property
    def fee_value(self) -> Decimal:
        if not self.process_rule_results:
            return Decimal("0.00")
        best_option = min(self.process_rule_results)
        if best_option.cancellation_possible:
            return best_option.fee
        return Decimal("0.00")


@dataclass(frozen=True)
class CancellationResult:
    position_result: PositionResult
    process_result: ProcessResult

    @classmethod
    def from_dict(cls, data: dict) -> "CancellationResult":
        return cls(
            position_result=PositionResult.from_dict(data["position_result"]),
            process_result=ProcessResult.from_dict(data["process_result"]),
        )

    @property
    def cancellation_possible(self) -> bool:
        return self.position_result.cancellation_possible and self.process_result.cancellation_possible


class Cancellation(models.Model):
    CREATED: Final = "CREATED"
    APPROVAL_PENDING: Final = "APPROVAL_PENDING"
    PERFORMED: Final = "PERFORMED"
    CANCELLED: Final = "CANCELLED"

    CANCELLATION_STATE = (
        (CREATED, _("Created")),
        (APPROVAL_PENDING, _("Approval pending")),
        (PERFORMED, _("Performed")),
        (CANCELLED, _("Cancelled")),
    )

    event = models.ForeignKey(
        Event,
        verbose_name=_("Event"),
        related_name="cancellations",
        on_delete=models.CASCADE
    )
    order = models.ForeignKey(
        Order,
        verbose_name=_("Order"),
        related_name="cancellations",
        on_delete=models.CASCADE
    )
    keep = models.ManyToManyField(
        to=OrderPosition,
        verbose_name=_("Positions to keep"),
    )
    evaluation_ts = models.DateTimeField(
        verbose_name=_("Cancellation datetime"),
        auto_now_add=True,
    )

    state = models.CharField(
        max_length=16,
        choices=CANCELLATION_STATE,
        default=CREATED,
        verbose_name=_("State of the cancellation"),
    )

    _result = models.JSONField(default=dict, db_column="result", encoder=DjangoJSONEncoder)

    @property
    def result(self) -> CancellationResult:
        return CancellationResult.from_dict(self._result)

    @result.setter
    def result(self, value: CancellationResult):
        if not isinstance(value, CancellationResult):
            raise TypeError("result must be a CancellationResult instance")
        if self._result:
            raise ValueError("result is write-once and has already been set")
        self._result = asdict(value)

    @property
    def possible(self) -> bool:
        return self.result.cancellation_possible

    @staticmethod
    def evaluate(event: Event, order: Order, keep: Set[OrderPosition],
                 check_ts: datetime.datetime) -> "CancellationResult":

        # validate that all keep order positions are part of the order
        for p in keep:
            if p.order_id != order.id:
                raise ValidationError("OrderPosition {} does not belong to order {}".format(p.code, order.code))

        # exclude canceled positions
        for p in order.positions.all():
            if p.canceled:
                keep.add(p)

        # collect all checks, position_rules and process_rules that are applicable
        checks = CancellationRule.collect_checks(event=event)
        position_rules: QuerySet[PositionCancellationRule] = PositionCancellationRule.objects.filter(
            event=event).with_rule_data().all()
        process_rules: QuerySet[ProcessCancellationRule] = ProcessCancellationRule.objects.filter(
            event=event).with_rule_data().all()

        order = CancellationRule.prefetch_order(event, order, checks)

        # keep track of all decisions so we can explain them in the logs
        position_check_results: Dict[int, List[CheckResult]] = {}
        position_rule_results: Dict[int, List[RuleResult]] = {}

        # perform all position checks and position rules
        for position in order.positions.all():
            position_check_results[position.id] = []
            position_rule_results[position.id] = []

            # skip this position if customer doesn't want to cancel
            if position in keep:
                continue

            # evaluate the system/plugin checks for the position
            for check in checks.position:
                res = check.evaluate(order=order, keep=keep, position=position, check_ts=check_ts)
                if res is not None:
                    position_check_results[position.id].append(res)

            # evaluate all customer specified rules for this position
            for rule in position_rules:
                result = rule.evaluate_position_rule(order, keep, position, check_ts)
                if result is not None:
                    position_rule_results[position.id].append(result)

        position_results = PositionResult(position_check_results=position_check_results,
                                          position_rule_results=position_rule_results)

        # we need the current fee_value to select the cheapest process rule
        temp_position_fees = position_results.fee_value

        # again keep track of all decisions so we can explain them in the logs
        process_check_results: List[CheckResult] = []
        process_rule_results: List[RuleResult] = []

        # evaluate all system/plugin provided checks for the cancellation process
        for check in checks.process:
            res = check.evaluate(order=order, keep=keep, position=None, check_ts=check_ts)
            if res is not None:
                process_check_results.append(res)

        # evaluate all customer specified rules for the cancellation process
        for rule in process_rules:
            result = rule.evaluate_process_rule(order, keep, temp_position_fees, check_ts)
            if result is not None:
                process_rule_results.append(result)

        process_result = ProcessResult(process_check_results=process_check_results,
                                       process_rule_results=process_rule_results)

        res = CancellationResult(position_result=position_results, process_result=process_result)

        return res

    @staticmethod
    def prepare(event: Event, order: Order, keep: Set[OrderPosition],
                check_ts: datetime.datetime) -> "Cancellation":
        res = Cancellation.evaluate(event=event, order=order, keep=set(), check_ts=check_ts)
        c = Cancellation(event=event, order=order, result=res, evaluation_ts=check_ts)
        c.save()
        c.keep.add(*keep)
        return c

    def execute(self):
        # TODO load the cancellation verdict from the id  and perform the actions
        pass


def _send_self_service_cancellation_checks(event: Event) -> List[Tuple[Any, Any]]:
    return self_service_cancellation_checks.send(sender=event)


class CancellationRuleQuerySet(models.QuerySet):
    def with_rule_data(self):
        model = self.model
        qs = self.prefetch_related(*[p() for p in model.rule_prefetches])
        if model.rule_related_selects:
            qs = qs.select_related(*model.rule_related_selects)
        return qs


class CancellationRuleManager(models.Manager.from_queryset(CancellationRuleQuerySet)):
    check_type: ClassVar[CheckTypes]

    def get_queryset(self):
        return super().get_queryset().filter(type=self.check_type).order_by("pk")


class CancellationRule(models.Model):
    EARLIEST: Final = "EARLIEST"
    LATEST: Final = "LATEST"

    SUBEVENT_VARIANT_CHOICES = (
        (EARLIEST, _("Earliest")),
        (LATEST, _("Latest")),
    )

    event = models.ForeignKey(
        Event,
        verbose_name=_("Event"),
        related_name="cancellation_rules",
        on_delete=models.CASCADE
    )

    type = models.CharField(
        verbose_name=_("Type of the cancellation rule"),
        default=CheckTypes.POSITION,
        choices=CheckTypes,
        max_length=15,
    )

    allowed_until = ModelRelativeDateTimeField(null=True, blank=True, verbose_name=_("Allowed until"))
    except_after = ModelRelativeDateTimeField(null=True, blank=True, verbose_name=_("Except after"))
    if TYPE_CHECKING:
        allowed_until: Optional[RelativeDateWrapper]
        except_after: Optional[RelativeDateWrapper]

    # --- position-only fields ---
    fee_percentage_per_position = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
        verbose_name=_("Fee Percentage per OrderPosition"),
        default=Decimal("0.00"),
    )
    fee_absolute_per_position = models.DecimalField(
        max_digits=13,
        decimal_places=2,
        verbose_name=_("Absolute fee per OrderPosition"),
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    all_products = models.BooleanField(
        verbose_name=_("All products and variations"),
        default=True,
    )
    limit_products = models.ManyToManyField(Item, verbose_name=_("Products"), blank=True)
    limit_variations = models.ManyToManyField(
        ItemVariation, blank=True, verbose_name=_("Variations")
    )

    # --- process-only fields ---
    subevent_variant = models.CharField(
        max_length=8,
        choices=SUBEVENT_VARIANT_CHOICES,
        default=EARLIEST,
        verbose_name=_("Subevent variant"),
        help_text=_("An order can contain tickets for multiple different events if the event has "
                    "subevents enabled. This choice controls if the order position for the earliest "
                    "or the latest point in time in the order is used to determine the allowed until and "
                    "except after dates.")
    )

    fee_cancellation_process = models.DecimalField(
        max_digits=13,
        decimal_places=2,
        verbose_name=_("Absolute fee per Cancellation"),
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    fee_mode = models.CharField(
        verbose_name=_("The method with which process and position fees are combined."),
        choices=[
            (FeeType.MINIMUM, FeeType.MINIMUM.label),
            (FeeType.ADDITIONAL, FeeType.ADDITIONAL.label),
        ],
        blank=True,
        null=True,
        max_length=15,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(type__in=[CheckTypes.POSITION, CheckTypes.PROCESS]),
                name="cancellation_rule_type_valid",
            ),
        ]

    @staticmethod
    def collect_checks(event: Event, send_fn: Callable[
        [Event], List[Tuple[Any, Any]]
    ] = _send_self_service_cancellation_checks) -> Checks:

        position_checks: List[CancellationCheck] = []
        process_checks: List[CancellationCheck] = []

        seen = set()
        for recv, resp in send_fn(event):
            if resp is None:
                continue

            if not isinstance(resp, CancellationCheck):
                raise ValueError('self_service_cancellation_checks received response of wrong type')
            if resp.id in seen:
                raise ValueError('self_service_cancellation_checks received multiple responses with the id')
            seen.add(resp.id)

            if resp.type == CheckTypes.POSITION:
                position_checks.append(resp)
            if resp.type == CheckTypes.PROCESS:
                process_checks.append(resp)

        return Checks(position=position_checks, process=process_checks)

    @staticmethod
    def prefetch_order(event: Event, order: Order, checks: Checks) -> Order:
        prefetches = [pref() for pref in [*checks.prefetches,
                                          *PositionCancellationRule.prefetches,
                                          *ProcessCancellationRule.prefetches]]

        related_selects = {*checks.related_selects,
                           *PositionCancellationRule.related_selects,
                           *ProcessCancellationRule.related_selects}

        qs = Order.objects.prefetch_related(*prefetches)
        if related_selects:
            qs = qs.select_related(*related_selects)

        return qs.get(event=event, id=order.id)

    @staticmethod
    def _resolve_date_field_common(
            date_field: RelativeDateWrapper,
            order: Order,
            resolve_subevent: Callable[[Any], Any],
    ) -> datetime.date | datetime.datetime:
        reldate_type = date_field.choice

        if reldate_type == "date":
            return make_aware(
                datetime.datetime.combine(date_field.date(order.event), datetime.time(hour=23, minute=59, second=59)),
                order.event.timezone,
            )
        elif reldate_type == "datetime":
            return date_field.datetime(order.event)

        if reldate_type.base == "order":
            return date_field.datetime(order)

        if not order.event.has_subevents:
            return date_field.datetime(order.event)

        return date_field.datetime(resolve_subevent(reldate_type))

    def clean(self):
        super().clean()
        errors = {}

        if self.type == CheckTypes.PROCESS:
            if self.fee_mode not in (FeeType.MINIMUM, FeeType.ADDITIONAL):
                errors["fee_mode"] = _(
                    "Fee mode is not valid on a process rule."
                )
            if self.fee_percentage_per_position or self.fee_absolute_per_position:
                errors["fee_percentage_per_position"] = _(
                    "Position fees must be unset on a process rule."
                )
            if self.pk and (self.limit_products.exists() or self.limit_variations.exists()):
                errors["limit_products"] = _(
                    "Product/variation limits are not valid on a process rule."
                )

        if self.type == CheckTypes.POSITION:
            if self.fee_cancellation_process:
                errors["fee_cancellation_process"] = _(
                    "Process fee must be unset on a position rule."
                )
            if self.fee_mode:
                errors["fee_mode"] = _(
                    "Fee mode is not valid on a position rule."
                )

        if errors:
            raise ValidationError(errors)


class PositionCancellationRuleManager(CancellationRuleManager):
    check_type = CheckTypes.POSITION


class PositionCancellationRule(CancellationRule):
    """
    PositionCancellationRules answer the questions:
    - Can this position be canceled?
    - What is the price for cancelling this position?
    """
    objects = PositionCancellationRuleManager()

    rule_prefetches: ClassVar[List[Callable[[], Prefetch]]] = [
        lambda: Prefetch('limit_products'),
        lambda: Prefetch('limit_variations'),
    ]
    rule_related_selects: ClassVar[List[str]] = []

    prefetches: ClassVar[List[Callable[[], Prefetch]]] = [
        lambda: Prefetch('all_positions__item'),
        lambda: Prefetch('event'),
    ]
    related_selects: ClassVar[List[str]] = []

    class Meta:
        proxy = True

    def save(self, *args, **kwargs):
        self.type = CheckTypes.POSITION
        self.full_clean()
        super().save(*args, **kwargs)

    def _position_matches_rule(self, position: OrderPosition) -> Optional[CheckResult]:
        with ensure_no_queries():
            res = CheckResult(
                id=f"position_rule_{self.id}",
                reason=_("Rule matches this product"),
                cancellation_possible=True
            )

            if self.all_products:
                return res

            item_pks = {item.pk for item in self.limit_products.all()}
            if position.item_id in item_pks:
                return res

            variation_pks = {variation.pk for variation in self.limit_variations.all()}
            if position.variation_id in variation_pks:
                return res

            return None

    @staticmethod
    def _resolve_date_field(date_field: RelativeDateWrapper, order: Order,
                            position: OrderPosition) -> datetime.date | datetime.datetime:
        return CancellationRule._resolve_date_field_common(
            date_field, order, resolve_subevent=lambda _reldate_type: position.subevent
        )

    def _evaluate_cancellation_moment(self, position: OrderPosition, check_ts: datetime.datetime) -> List[CheckResult]:
        check_results = []

        order = position.order

        for param in ('allowed_until', 'except_after'):
            value: RelativeDateWrapper | None = getattr(self, param, None)
            if value is not None:
                if check_ts <= self._resolve_date_field(value, order, position):
                    check_results.append(
                        CheckResult(
                            id=f"position_rule_{self.id}_{param}",
                            reason=_("{} is earlier than {} cutoff {}".format(check_ts, param, value)),
                            cancellation_possible=True
                        )
                    )
                else:
                    check_results.append(
                        CheckResult(
                            id=f"position_rule_{self.id}_{param}",
                            reason=_("{} is later than {} cutoff {}".format(check_ts, param, value)),
                            cancellation_possible=False
                        )
                    )
            else:
                check_results.append(
                    CheckResult(
                        id=f"position_rule_{self.id}_{param}",
                        reason=_("No {} limit defined".format(param)),
                        cancellation_possible=True
                    )
                )

        return check_results

    def evaluate_position_rule(self, order: Order, _keep: Set[OrderPosition], position: OrderPosition,
                               check_ts: datetime.datetime) -> Optional[RuleResult]:
        rule_check_results = []
        match = self._position_matches_rule(position)
        if match:
            rule_check_results.append(match)
        rule_check_results.extend(self._evaluate_cancellation_moment(position, check_ts))

        if self.fee_percentage_per_position and self.fee_absolute_per_position:
            raise NotImplementedError(
                "Combination of fee_percentage_per position and fee_absolute_per_position is not valid")
        elif self.fee_absolute_per_position != Decimal(0.00):
            return RuleResult.from_absolute_fee(
                id=self.id,
                partial_results=rule_check_results,
                fee_type=FeeType.POSITION,
                absolute_fee=self.fee_absolute_per_position
            )
        else:
            return RuleResult.from_relative_fee(
                id=self.id,
                partial_results=rule_check_results,
                fee_type=FeeType.POSITION,
                position_price=position.price,
                percentage=self.fee_percentage_per_position,
                currency=order.event.currency
            )


class ProcessCancellationRuleManager(CancellationRuleManager):
    check_type = CheckTypes.PROCESS


class ProcessCancellationRule(CancellationRule):
    """
    ProcessCancellationRules answer the question:
    - What is the processing fee for performing this cancellation?
    """

    objects = ProcessCancellationRuleManager()

    rule_prefetches: ClassVar[List[Callable[[], Prefetch]]] = []
    rule_related_selects: ClassVar[List[str]] = []

    prefetches: ClassVar[List[Callable[[], Prefetch]]] = [
        lambda: Prefetch('event'),
    ]
    related_selects: ClassVar[List[str]] = []

    class Meta:
        proxy = True

    def save(self, *args, **kwargs):
        self.type = CheckTypes.PROCESS
        self.full_clean()
        super().save(*args, **kwargs)

    @staticmethod
    def _resolve_date_field(date_field: RelativeDateWrapper, order: Order,
                            mode: Literal["EARLIEST", "LATEST"] | str) -> datetime.date | datetime.datetime:
        if mode not in ('EARLIEST', 'LATEST'):
            raise ValidationError('Mode is invalid')

        comparators = {
            "EARLIEST": operator.lt,
            "LATEST": operator.gt,
        }
        compare = comparators[mode]

        def resolve_subevent(reldate_type):
            base_event = order.event
            base_value: None | datetime.date = None
            for pos in order.positions.all():
                e = pos.subevent if pos.subevent else pos.event
                value = getattr(e, reldate_type.attribute)
                if value is None:
                    continue  # skip when there is no value
                if base_value is None or compare(value, base_value):
                    base_event = e
                    base_value = value
            return base_event

        return CancellationRule._resolve_date_field_common(date_field, order, resolve_subevent)

    def _evaluate_cancellation_moment(self, order: Order, check_ts: datetime.datetime) -> List[CheckResult]:

        check_results: List[CheckResult] = []

        for param in ('allowed_until', 'except_after'):
            value: RelativeDateWrapper | None = getattr(self, param, None)
            if value is not None:
                if check_ts <= self._resolve_date_field(value, order, self.subevent_variant):
                    check_results.append(
                        CheckResult(
                            id=f"process_rule_{self.id}_{param}",
                            reason=_("{} is earlier than {} cutoff {}".format(check_ts, param, value)),
                            cancellation_possible=True
                        )
                    )
                else:
                    check_results.append(
                        CheckResult(
                            id=f"process_rule_{self.id}_{param}",
                            reason=_("{} is later than {} cutoff {}".format(check_ts, param, value)),
                            cancellation_possible=False
                        )
                    )
            else:
                check_results.append(
                    CheckResult(
                        id=f"process_rule_{self.id}_{param}",
                        reason=_("No {} limit defined".format(param)),
                        cancellation_possible=True
                    )
                )
        return check_results

    def evaluate_process_rule(self, order: Order, _keep: Set[OrderPosition], position_fees: Decimal,
                              check_ts: datetime.datetime) -> Optional[RuleResult]:
        fee_mode = self.fee_mode
        if fee_mode not in (FeeType.MINIMUM, FeeType.ADDITIONAL):
            raise ValueError(f"Unexpected fee_mode: {fee_mode!r}")

        check_results: List[CheckResult] = self._evaluate_cancellation_moment(order, check_ts)

        return RuleResult.from_process_fee(
            id=self.id,
            partial_results=check_results,
            fee_type=fee_mode,
            absolute_fee=self.fee_cancellation_process,
            reference_price=position_fees,
        )
