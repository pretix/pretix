
from dataclasses import dataclass
from decimal import Decimal
from functools import reduce
from typing import Callable, Dict, List, Literal, Optional, Set

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _

from pretix.base.decimal import round_decimal
from pretix.base.models import Event, Item, ItemVariation, Order, OrderPosition
from pretix.base.reldate import ModelRelativeDateTimeField
from pretix.base.timemachine import time_machine_now


@dataclass(frozen=True)
class CancellationCheckResult:
    cancellation_possible: bool
    reason: str


# Maps Check identifier → cancellation check result
CancellationCheckResultsById = Dict[str, CancellationCheckResult]


CheckFn = Callable[[Order, Set[OrderPosition], Optional[OrderPosition]], CancellationCheckResultsById]

FeeType = Literal['position_fee', 'process_fee']


class Ruling:
    """
    A Ruling is the result of applying a CancellationRule onto an Order or OrderPosition.
    """
    rule_id: int
    results: CancellationCheckResultsById
    fee_type: FeeType
    fee: Decimal
    cancellation_possible: bool

    def __init__(
            self,
            rule_id: int,
            results: CancellationCheckResultsById,
            fee_type: FeeType,
            fee: Decimal
    ):
        self.rule_id = rule_id
        self.results = results
        self.fee_type = fee_type
        self.fee = fee
        self.cancellation_possible = all(ruling.cancellation_possible for ruling in results.values())

    @classmethod
    def from_absolute_fee(
            cls,
            rule_id: int,
            results: CancellationCheckResultsById,
            fee_type: FeeType,
            absolute_fee: Decimal
    ) -> "Ruling":
        """
        Constructs a Ruling with an absolute fee.
        :param rule_id: Id of the rule
        :param results: CheckResult object
        :param fee_type: If the fee is calculated for a position or process fee
        :param absolute_fee: amount of the fee
        :return:
        """
        return Ruling(rule_id=rule_id, results=results, fee_type=fee_type, fee=absolute_fee)

    @classmethod
    def from_relative_fee(
            cls,
            rule_id: int,
            results: CancellationCheckResultsById,
            fee_type: Literal['position_fee'],
            reference_price: Decimal,
            percentage: Decimal,
            currency: str
    ) -> "Ruling":
        """
        Constructs a Ruling with an absolute fee.
        :param rule_id: ID of the rule
        :param results: CheckResult object
        :param fee_type: Must be a position_fee as the fee can only be in reference to a position
        :param reference_price: Price of the position to reference
        :param percentage: Percentage of the reference_price set as the fee
        :param currency: Currency of the reference_price, used for correct rounding of the fee
        :return:
        """
        if fee_type == "process_fee":
            raise ValidationError("Process fee cannot be used with relative fees")

        return Ruling(
            rule_id=rule_id,
            results=results,
            fee_type=fee_type,
            fee=round_decimal(reference_price * (percentage / 100), currency)
        )

    def __lt__(self, other):
        if not isinstance(other, Ruling):
            return NotImplemented

        if self.fee_type != other.fee_type:
            return NotImplemented

        if self.cancellation_possible == other.cancellation_possible:
            return self.fee < other.fee
        else:
            return self.cancellation_possible and not other.cancellation_possible


class CancellationRule(models.Model):
    event = models.ForeignKey(
        Event,
        verbose_name=_("Event"),
        related_name="orders",
        on_delete=models.CASCADE
    )

    all_products = models.BooleanField(
        verbose_name=_("All products and variations"),
        default=True,
    )
    limit_products = models.ManyToManyField(Item, verbose_name=_("Products"), blank=True)
    limit_variations = models.ManyToManyField(
        ItemVariation, blank=True, verbose_name=_("Variations")
    )


    allowed_until = ModelRelativeDateTimeField(null=True, blank=True)
    except_after = ModelRelativeDateTimeField(null=True, blank=True)

    fee_percentage_per_item = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator("0.00"), MaxValueValidator("100.00")],
        verbose_name=_("Fee Percentage per OrderPosition"),
        default=Decimal("0.00"),
    )  # wird als sum() kombiniert
    fee_absolute_per_item = models.DecimalField(
        max_digits=13,
        decimal_places=2,
        verbose_name=_("Absolute fee per OrderPosition"),
        default=Decimal("0.00"),
    )  # wird als sum() kombiniert

    fee_cancellation_process = models.DecimalField(
        max_digits=13,
        decimal_places=2,
        verbose_name=_("Absolute fee per Cancellation"),
        default=Decimal("0.00"),
    )  # wird als max() kombiniert

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.checks: List[CheckFn] = [self._check_time_window]


    # TODO implement order status check

    def _check_time_window(self, order: Order, keep: Set[OrderPosition], position: OrderPosition) -> CancellationCheckResultsById:
        check_id = "TIME_WINDOW"

        if not self.allowed_until and not self.allowed_until:
            return {check_id: CancellationCheckResult(
                cancellation_possible=True,
                reason="No time window specified",
            )}

        relevant_event = position.subevent or position.event
        in_allowed_until = time_machine_now() < self.allowed_until.datetime(
            relevant_event) if self.allowed_until else False
        in_exemption = time_machine_now() > self.except_after.datetime(
            relevant_event) if self.except_after else False

        if in_allowed_until and not in_exemption:
            except_after_message = f" and not after {self.except_after.datetime(relevant_event)}" if self.except_after else ""
            return {check_id: CancellationCheckResult(
                cancellation_possible=True,
                reason=f"Cancellation in required time window before {self.allowed_until.datetime(relevant_event)}{except_after_message}",
            )}
        elif in_allowed_until and in_exemption:
            return {check_id: CancellationCheckResult(
                cancellation_possible=False,
                reason=f"Cancellation in exemption period after {self.except_after.datetime(relevant_event)}",
            )}
        else:
            return {check_id: CancellationCheckResult(
                cancellation_possible=False,
                reason=f"Cancellation after time window ending on {self.allowed_until.datetime(relevant_event)}",
            )}

    def check(self, system_check_results: List[CancellationCheckResult], order: Order, keep: Set[OrderPosition], position: OrderPosition) -> Optional[Ruling]:
        if not self.all_products and position.item_id not in self.limit_products.values_list('pk', flat=True):
            return None

        if not self.all_products and position.variation_id not in self.limit_variations.values_list('pk', flat=True):
            return None

        check_results = [check(order, keep, position) for check in self.checks]

        if self.fee_percentage_per_item and self.fee_absolute_per_item:
            raise NotImplementedError("Should never be reached")
        elif self.fee_absolute_per_item != Decimal(0.00):
            return Ruling.from_absolute_fee(
                    rule_id=self.id,
                    results=reduce(lambda a, b: a | b, [*system_check_results, *check_results], {}),
                    fee_type='position_fee',
                    absolute_fee=self.fee_absolute_per_item
                )
        else:
            return Ruling.from_relative_fee(
                    rule_id=self.id,
                    results=reduce(lambda a, b: a | b, [*system_check_results, *check_results], {}),
                    fee_type='position_fee',
                    reference_price=position.price,
                    percentage=self.fee_absolute_per_item,
                    currency=order.event.currency
                )


class CancellationCheck:
    id: str
    prefetches: List[Prefetch] = []
    related_selects: List[str] = []

    def check(self, order: Order, keep: Set[OrderPosition], order_position: OrderPosition) -> CancellationCheckResult:
        raise NotImplementedError()
