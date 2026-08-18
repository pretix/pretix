import datetime
import operator
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import chain
from typing import (
    Any, Callable, ClassVar, Dict, Final, List, Literal, Optional, Protocol, Set,
    TYPE_CHECKING, Tuple, TypeAlias,
)
from django_stubs_ext import StrOrPromise

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _

from pretix.base.decimal import round_decimal
from pretix.base.models import Event, Item, ItemVariation, Order, OrderPosition
from pretix.base.reldate import ModelRelativeDateTimeField, RelativeDateWrapper
from pretix.base.signals import self_service_cancellation_checks

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
        return list(chain([check.prefetches for check in [*self.position, *self.process]]))

    @property
    def related_selects(self) -> List[str]:
        return list(chain([check.related_selects for check in [*self.position, *self.process]]))


PositionSet: TypeAlias = Set[OrderPosition]


class PositionCheckFn(Protocol):
    def __call__(self, order: Order, keep: PositionSet, position: OrderPosition, /) -> CheckResult:
        ...


class ProcessCheckFn(Protocol):
    def __call__(self, order: Order, keep: PositionSet, /) -> CheckResult:
        ...


@dataclass(frozen=True)
class CancellationCheck:
    id: str
    type: CheckTypes
    check_fn: PositionCheckFn | ProcessCheckFn = field(compare=False)
    prefetches: List[Callable[[], Prefetch]] = field(default_factory=list)
    related_selects: List[str] = field(default_factory=list)

    def evaluate(self, order: Order, keep: PositionSet,
                 position: OrderPosition | None) -> CheckResult:
        if position and self.type == CheckTypes.POSITION:
            return self.check_fn(order, keep, position)
        elif position is None and self.type == CheckTypes.PROCESS:
            return self.check_fn(order, keep)
        else:
            raise ValidationError("Type of the rule doesn't match the check_fn")


@dataclass(frozen=True)
class PositionResult:
    position_check_results: Dict[int, List[CheckResult]]
    position_rule_results: Dict[int, List[RuleResult]]

    @property
    def cancellation_possible(self) -> bool:
        def ok(results: List[CheckResult] | List[RuleResult]) -> bool:
            return all([val.cancellation_possible for val in results]) if results else True

        return all(
            ok(results)
            for d in
            (self.position_check_results, {key: [min(pos_res)] for key, pos_res in self.position_rule_results.items()})
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

    @property
    def cancellation_possible(self) -> bool:
        best_option = min(self.process_rule_results)
        return all([res.cancellation_possible for res in [*self.process_check_results, best_option]])

    @property
    def fee_value(self) -> Decimal:
        best_option = min(self.process_rule_results)
        if best_option.cancellation_possible:
            return best_option.fee
        return Decimal("0.00")


@dataclass(frozen=True)
class CancellationResult:
    position_result: PositionResult
    process_result: ProcessResult

    @property
    def cancellation_possible(self) -> bool:
        return self.position_result.cancellation_possible and self.process_result.cancellation_possible

    def remember_cancellation(self):
        # TODO: store the cancellation verdict in the session storage for X Minutes
        pass

    def perform_cancellation(self, order: Order, keep: Set[int]):
        # TODO load the cancellation verdict from the session and perform the actions
        pass


def _send_self_service_cancellation_checks(event: Event) -> List[Tuple[Any, Any]]:
    return self_service_cancellation_checks.send(sender=event)


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
        related_name="cancellation_rule",
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
        validators=[MinValueValidator("0.00"), MaxValueValidator("100.00")],
        verbose_name=_("Fee Percentage per OrderPosition"),
        default=Decimal("0.00"),
    )
    fee_absolute_per_position = models.DecimalField(
        max_digits=13,
        decimal_places=2,
        verbose_name=_("Absolute fee per OrderPosition"),
        default=Decimal("0.00"),
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
    )

    fee_mode = models.CharField(
        verbose_name=_("Restrict to check-in status"),
        default=FeeType.MINIMUM,
        choices=[
            (FeeType.MINIMUM, FeeType.MINIMUM.label),
            (FeeType.ADDITIONAL, FeeType.ADDITIONAL.label),
        ],
        max_length=15,
    )

    prefetches: ClassVar[List[Callable[[], Prefetch]]] = []
    related_selects: ClassVar[List[str]] = []

    @staticmethod
    def _collect_checks(event: Event, send_fn: Callable[
        [Event], List[Tuple[Any, Any]]
    ] = _send_self_service_cancellation_checks) -> Checks:
        position_checks: List[CancellationCheck] = []
        process_checks: List[CancellationCheck] = []

        seen = set()
        for recv, resp in send_fn(event):
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
    def evaluate(event: Event, order: Order, keep: Set[OrderPosition]) -> "CancellationResult":
        # collect all checks, position_rules and process_rules that are applicable
        checks = CancellationRule._collect_checks(event=event)
        position_rules = PositionCancellationRule.objects.filter(event=event, type=CheckTypes.POSITION)
        process_rules = ProcessCancellationRule.objects.filter(event=event, type=CheckTypes.PROCESS)

        order = CancellationRule._prefetch_order(event, order, checks)

        # keep track of all decisions so we can explain them in the logs
        position_check_results: Dict[int, List[CheckResult]] = {}
        position_rule_results: Dict[int, List[RuleResult]] = {}

        # perform all position checks and position rules
        for position in order.positions.all():
            position_check_results[position.id] = []
            position_rule_results[position.id] = []

            # skip this position if customer doesn't want to cancel
            if position.id in keep:
                continue

            # evaluate the system/plugin checks for the position
            for check in checks.position:
                position_check_results[position.id].append(check.evaluate(order=order, keep=keep, position=position))

            # evaluate all customer specified rules for this position
            for rule in position_rules:
                result = rule.evaluate_position_rule(order=order, keep=keep, position=position)
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
            process_check_results.append(check.evaluate(order=order, keep=keep, position=None))

        # evaluate all customer specified rules for the cancellation process
        for rule in process_rules:
            result = rule.evaluate_process_rule(order=order, keep=keep, position_fees=temp_position_fees)
            if result is not None:
                process_rule_results.append(result)

        process_result = ProcessResult(process_check_results=process_check_results,
                                       process_rule_results=process_rule_results)

        return CancellationResult(position_result=position_results, process_result=process_result)

    @staticmethod
    def _prefetch_order(event: Event, order: Order, checks: Checks) -> Order:
        prefetches = [pref() for pref in [*chain(*checks.prefetches),
                                          *chain(*PositionCancellationRule.prefetches),
                                          *chain(*ProcessCancellationRule.prefetches)]]

        related_selects = {*chain(*checks.related_selects),
                           *chain(*PositionCancellationRule.related_selects),
                           *chain(*ProcessCancellationRule.related_selects)}

        order = Order.objects.prefetch_related(*prefetches).select_related(*related_selects).get(event=event,
                                                                                                 id=order.id)
        return order

    def clean(self):
        super().clean()
        errors = {}

        if self.type == CheckTypes.PROCESS:
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class PositionCancellationRuleManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(type=CheckTypes.POSITION)


class PositionCancellationRule(CancellationRule):
    """
    PositionCancellationRules answer the questions:
    - Can this position be canceled?
    - What is the price for cancelling this position?
    """
    objects = PositionCancellationRuleManager()

    prefetches: ClassVar[List[Callable[[], Prefetch]]] = []
    related_selects: ClassVar[List[str]] = []

    class Meta:
        proxy = True

    def save(self, *args, **kwargs):
        self.type = CheckTypes.POSITION
        self.full_clean()
        super().save(*args, **kwargs)

    def evaluate_position_rule(self, order: Order, keep: Set[OrderPosition], position: OrderPosition) -> Optional[
        RuleResult
    ]:
        if not self.all_products and position.item_id not in self.limit_products.values_list('pk', flat=True):
            return None

        if not self.all_products and position.variation_id not in self.limit_variations.values_list('pk', flat=True):
            return None

        rule_results = []  # TODO really evaluate rules

        if self.fee_percentage_per_position and self.fee_absolute_per_position:
            raise NotImplementedError(
                "Combination of fee_percentage_per position and fee_absolute_per_position is not valid")
        elif self.fee_absolute_per_position != Decimal(0.00):
            return RuleResult.from_absolute_fee(
                id=self.id,
                partial_results=rule_results,
                fee_type=FeeType.POSITION,
                absolute_fee=self.fee_absolute_per_position
            )
        else:
            return RuleResult.from_relative_fee(
                id=self.id,
                partial_results=rule_results,
                fee_type=FeeType.POSITION,
                position_price=position.price,
                percentage=self.fee_absolute_per_position,
                currency=order.event.currency
            )


class ProcessCancellationRuleManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(type=CheckTypes.PROCESS)

class ProcessCancellationRule(CancellationRule):
    """
    ProcessCancellationRules answer the question:
    - What is the processing fee for performing this cancellation?
    """

    objects = ProcessCancellationRuleManager()

    prefetches: ClassVar[List[Callable[[], Prefetch]]] = []
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
        reldate_type = date_field.choice

        if mode not in ('EARLIEST', 'LATEST'):
            raise ValidationError('Mode is invalid')

        if reldate_type == "date":
            return date_field.date(order.event)
        elif reldate_type == "datetime":
            return date_field.datetime(order.event)

        if reldate_type.base == "order":
            return date_field.datetime(order)

        if not order.event.has_subevents:
            return date_field.datetime(order.event)

        comparators = {
            "EARLIEST": operator.lt,
            "LATEST": operator.gt,
        }

        compare = comparators[mode]
        base_event = order.event
        base_value: None | datetime.date | datetime.date = None

        for pos in order.positions.all():
            e = pos.subevent if pos.subevent else pos.event
            value = getattr(e, reldate_type.attribute)

            if value is None:
                continue  # skip when there is no value

            if base_value is None or compare(value, base_value):
                base_event = e
                base_value = value

        return date_field.datetime(base_event)


    def evaluate_process_rule(self, order: Order, keep: Set[OrderPosition], position_fees: Decimal) -> \
            Optional[RuleResult]:
        fee_mode = self.fee_mode
        if fee_mode not in (FeeType.MINIMUM, FeeType.ADDITIONAL):
            raise ValueError(f"Unexpected fee_mode: {fee_mode!r}")

        check_results: List[CheckResult] = []

        now = datetime.datetime.now(tz=datetime.timezone.utc)

        for param in ('allowed_until', 'except_after'):
            value: RelativeDateWrapper | None = getattr(self, param, None)
            if value is not None:
                if now <= self._resolve_date_field(value, order, self.subevent_variant):
                    check_results.append(
                        CheckResult(
                            id=f"process_rule_{self.id}",
                            reason=_("{} is earlier than {} cutoff {}".format(now, param, value)),
                            cancellation_possible=True
                        )
                    )
                else:
                    check_results.append(
                        CheckResult(
                            id=f"process_rule_{self.id}",
                            reason=_("{} is later than {} cutoff {}".format(now, param, value)),
                            cancellation_possible=False
                        )
                    )
            else:
                check_results.append(
                    CheckResult(
                        id=f"process_rule_{self.id}",
                        reason=_("No {} limit defined".format(param)),
                        cancellation_possible=True
                    )
                )

            return RuleResult.from_process_fee(
                id=self.id,
                partial_results=check_results,
                fee_type=fee_mode,
                absolute_fee=self.fee_cancellation_process,
                reference_price=position_fees,
            )
