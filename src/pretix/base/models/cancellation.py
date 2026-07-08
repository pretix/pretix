from abc import ABC
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Literal, NamedTuple, Optional, Protocol, Set, TYPE_CHECKING, TypeAlias

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _

from pretix.base.decimal import round_decimal
from pretix.base.models import Event, Item, ItemVariation, Order, OrderPosition
from pretix.base.reldate import ModelRelativeDateTimeField
from pretix.base.signals import self_service_cancellation_checks


class FeeType(models.TextChoices):
    MINIMUM = "min_process_fee", _("Minimum total fee")
    ADDITIONAL = "add_process_fee", _("Additional fee")
    POSITION = "position_fee", _("Position fee")


class RuleTypes(models.TextChoices):
    POSITION = "position", _("Order Position Cancellation Rule")
    PROCESS = "process", _("Cancellation Process Rule")


@dataclass(frozen=True)
class CheckResult:
    id: str
    reason: str
    cancellation_possible: bool
    type: Literal['check'] = field(default="check")

    @property
    def key(self) -> str:
        return f"{self.type}::{self.id}"


@dataclass(frozen=True)
class RuleResult:
    id: int
    partial_results: List[CheckResult]
    fee_type: FeeType
    fee: Decimal

    type: Literal['rule'] = field(default="rule")

    @property
    def key(self) -> str:
        return f"{self.type}::{self.id}"

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
        fee = Decimal(0)
        if fee_type == FeeType.MINIMUM:
            if reference_price < absolute_fee:
                fee = absolute_fee - reference_price
            else:
                fee = reference_price
        elif fee_type == FeeType.ADDITIONAL:
            fee = absolute_fee

        return RuleResult(id=id, partial_results=partial_results, fee_type=fee_type, fee=fee)

    def __lt__(self, other):
        if not isinstance(other, RuleResult):
            return NotImplemented

        if self.fee_type != other.fee_type:
            return NotImplemented

        if self.cancellation_possible == other.cancellation_possible:
            return self.fee < other.fee
        else:
            return self.cancellation_possible and not other.cancellation_possible


class Checks(NamedTuple):
    position: List["CancellationCheck"]
    process: List["CancellationCheck"]


PositionSet: TypeAlias = Set[OrderPosition]


class PositionCheckFn(Protocol):
    def __call__(self, order: Order, keep: PositionSet, position: OrderPosition) -> CheckResult: ...


class ProcessCheckFn(Protocol):
    def __call__(self, order: Order, keep: PositionSet) -> CheckResult: ...


@dataclass(frozen=True)
class CancellationCheck(ABC):
    id: str
    type: RuleTypes
    check_fn: PositionCheckFn | ProcessCheckFn
    prefetches: List[Prefetch] = field(default_factory=list)
    related_selects: List[str] = field(default_factory=list)

    def evaluate(self, order: Order, keep: PositionSet,
                 position: OrderPosition | None) -> CheckResult:
        if position and self.type == RuleTypes.POSITION:
            return self.check_fn(order, keep, position)
        elif position is None and self.type == RuleTypes.PROCESS:
            return self.check_fn(order, keep)
        else:
            raise ValidationError("Type of the rule doesn't match the check_fn")


class CancellationRule(models.Model):
    event = models.ForeignKey(
        Event,
        verbose_name=_("Event"),
        related_name="cancellation_rule",
        on_delete=models.CASCADE
    )

    type = models.CharField(
        verbose_name=_("Type of the cancellation rule"),
        default=RuleTypes.POSITION,
        choices=RuleTypes,
        max_length=15,
    )

    allowed_until = ModelRelativeDateTimeField(null=True, blank=True)
    except_after = ModelRelativeDateTimeField(null=True, blank=True)

    @staticmethod
    def _collect_checks(event: Event) -> Checks:
        position_checks: List[CancellationCheck] = []
        process_checks: List[CancellationCheck] = []
        seen = set()
        for recv, resp in self_service_cancellation_checks.send(sender=event):
            if not isinstance(recv, CancellationCheck):
                raise ValueError('self_service_cancellation_checks received response of wrong type')
            if resp.id in seen:
                raise ValueError('self_service_cancellation_checks received multiple responses with the id')
            seen.add(resp.id)

            if resp.type == RuleTypes.POSITION:
                position_checks.append(resp)
            if resp.type == RuleTypes.PROCESS:
                process_checks.append(resp)

        return Checks(position=position_checks, process=process_checks)

    @staticmethod
    def evaluate(event: Event, order: Order, positions_to_keep: Set[int]):
        # collect all position checks and all process_checks
        checks = CancellationRule._collect_checks(event=event)

        # TODO prefetch the order
        # TODO set keep to Set[OrderPosition]
        keep: Set[OrderPosition] = set()

        position_rules = PositionCancellationRule.objects.filter(event=event, type=RuleTypes.POSITION)
        process_rules = ProcessCancellationRule.objects.filter(event=event, type=RuleTypes.PROCESS)

        # keep track of all decisions so we can explain them in the logs
        position_check_results: Dict[int, List[CheckResult]] = {}
        position_rule_results: Dict[int, List[RuleResult]] = {}
        process_check_results: List[CheckResult] = []
        process_rule_results: List[RuleResult] = []

        total_pos_fees = Decimal(0)
        # perform position checks
        for position in order.positions.all():
            position_check_results[position.id] = []
            position_rule_results[position.id] = []

            # skip this position if customer doesn't want to cancel
            if position.id in keep:
                continue

            # evaluate the system provided system checks for the position
            for check in checks.position:
                position_check_results[position.id].append(check.evaluate(order=order, keep=keep, position=position))

            # evaluate all customer specified rules for this position
            for rule in position_rules:
                result = rule.evaluate_position_rule(order=order, keep=keep, position=position)
                if result is not None:
                    position_rule_results[position.id].append(result)

            # get the cheapest rulings and sum up their fees
            position_rule_results[position.id].sort()
            best_option = position_rule_results[position.id][0]
            if best_option.cancellation_possible:
                total_pos_fees += best_option.fee

        # evaluate all system provided checks for the cancellation process
        for check in checks.process:
            process_check_results.append(check.evaluate(order=order, keep=keep, position=None))

        # evaluate all customer specified rules for the cancellation process
        for rule in process_rules:
            result = rule.evaluate_process_rule(order=order, keep=keep, position_fees=total_pos_fees)
            if result is not None:
                process_rule_results.append(result)
        process_rule_results.sort()

        return CancellationResult(position_check_results=position_check_results, pos)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class PositionCancellationRule(CancellationRule):
    """
    PositionCancellationRules answer the questions:
    - Can this position be canceled?
    - What is the price for cancelling this position?
    """

    class Meta:
        abstract = True

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

    if TYPE_CHECKING:
        allowed_until = ModelRelativeDateTimeField(null=True, blank=True)
        except_after = ModelRelativeDateTimeField(null=True, blank=True)

    def evaluate_position_rule(self, order: Order, keep: Set[OrderPosition], position: OrderPosition) -> Optional[
        RuleResult]:
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


class ProcessCancellationRule(CancellationRule):
    """
    ProcessCancellationRules answer the question:
    - What is the processing fee for performing this cancellation?
    """

    class Meta:
        abstract = True

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

    if TYPE_CHECKING:
        allowed_until = ModelRelativeDateTimeField(null=True, blank=True)
        except_after = ModelRelativeDateTimeField(null=True, blank=True)

    def evaluate_process_rule(self, order: Order, keep: Set[OrderPosition], position_fees: Decimal) -> \
            Optional[RuleResult]:

        rule_results = []  # TODO really evaluate rules

        fee_type = self.fee_mode
        if fee_type not in (FeeType.MINIMUM, FeeType.ADDITIONAL):
            raise ValueError(f"Unexpected fee_mode: {fee_type!r}")

        return RuleResult.from_process_fee(
            id=self.id,
            partial_results=rule_results,
            fee_type=fee_type,
            absolute_fee=self.fee_cancellation_process,
            reference_price=position_fees,
        )


@dataclass(frozen=True)
class CancellationResult:
    position_check_results: Dict[int, List[CheckResult]]
    position_rule_results: Dict[int, List[RuleResult]]
    process_check_results: List[CheckResult]
    process_rule_results: List[RuleResult]

    def _position_checks_passed(self) -> bool:
        passed: List[bool] = []
        for pos, results in self.position_check_results.items():
            # customer did not wish to cancel this position
            if len(results) == 0:
                passed += True
            else:
                passed += results[0].cancellation_possible
        return all(passed)

    def _position_rules_passed(self) -> bool:
        passed: List[bool] = []
        for pos, results in self.position_rule_results.items():
            # customer did not wish to cancel this position
            if len(results) == 0:
                passed += True
            else:
                passed += results[0].cancellation_possible
        return all(passed)

    def _process_checks_passed(self) -> bool:
        return all([res.cancellation_possible for res in self.process_check_results])

    def _process_rules_passed(self) -> bool:
        return all([res.cancellation_possible for res in self.process_rule_results])

    def cancellation_possible(self) -> bool:
        return self._position_checks_passed() and self._position_rules_passed() and self._process_checks_passed() and self._process_rules_passed()

    def remember_cancellation(self):
        # TODO: store the cancellation verdict in the session storage for X Minutes
        pass

    def perform_cancellation(self, order: Order, keep: Set[int]):
        # TODO load the cancellation verdict from the session and perform the actions
        pass
