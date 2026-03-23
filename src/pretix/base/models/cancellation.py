import dataclasses
from dataclasses import dataclass
from decimal import Decimal
from functools import reduce
from typing import Callable, Dict, List, Set, Union

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager

from pretix.base.models import Event, Order, OrderPosition
from pretix.base.reldate import ModelRelativeDateTimeField
from pretix.base.timemachine import time_machine_now


@dataclass(frozen=True)
class AbsoluteFee:
    amount: Decimal


@dataclass(frozen=True)
class RelativeFee:
    reference_price: Decimal
    percentage: Decimal

    @property
    def amount(self):
        return self.reference_price * (self.percentage/100)


Fee=Union[AbsoluteFee, RelativeFee]

@dataclass(frozen=True)
class OrderDiff:
    order: Order
    prev: Set[OrderPosition]
    next: Set[OrderPosition]

    def cancellations(self):
        return self.prev.difference(self.next)

    @staticmethod
    def cancel_all(order: Order) -> "OrderDiff":
        return OrderDiff(order=order, prev=set(order.positions.all()), next=set())

@dataclass(frozen=True)
class CheckRes:
    cancellation_possible: bool
    reason: str

CheckResult=Dict[str, CheckRes]


CheckFn=Callable[[OrderDiff, OrderPosition], CheckResult]


def merge_check_results(a: CheckResult, b: CheckResult) -> CheckResult:
    result = dict(a)
    for key, b_inner in b.items():
        if key in result:
            result[key] = result[key] | b_inner
        else:
            result[key] = b_inner
    return result


@dataclass(frozen=True)
class Ruling:
    rule_id: int
    results: CheckResult
    order_fee: Decimal=dataclasses.field(default_factory=lambda: Decimal(0))
    position_fee: Fee=dataclasses.field(default_factory=lambda: AbsoluteFee(Decimal(0)))

    cancellation_possible: bool=dataclasses.field(init=False)

    def __post_init__(self):
        object.__setattr__(
            self,
            'cancellation_possible',
            all(ruling.cancellation_possible
                for ruling in self.results.values()
            )
        )

    @property
    def total_fee(self):
        return self.position_fee.amount + self.order_fee

    def __lt__(self, other):
        if not isinstance(other, Ruling):
            return NotImplemented

        if self.cancellation_possible == other.cancellation_possible:
            return self.total_fee < other.total_fee
        else:
            return self.cancellation_possible and not other.cancellation_possible


class CancellationRuleQuerySet(models.QuerySet):
    def cancellation_possible(self, diff: OrderDiff):
        verdicts = [v[0] for v in self._evaluate(diff)]
        return all(v.cancellation_possible for v in verdicts), verdicts

    def _evaluate(self, diff: OrderDiff) -> List[List[Ruling]]:
        return [self._evaluate_op(diff, position) for position in diff.order.positions.all()]

    def _evaluate_op(self, diff: OrderDiff, order_position: OrderPosition) -> List[Ruling]:
        consequences = []
        for rule in self:
            if order_position.item in rule.items.all() or order_position.variation in rule.variations.all():
                consequences.append(rule.apply(diff, order_position))
        consequences.sort()
        return consequences


def validate_status_chars(value):
    invalid=set(value) - Order.ALLOWED_STATUS_CHARS
    if invalid:
        raise ValidationError(
            f"Invalid characters: {invalid}. Allowed: {Order.ALLOWED_STATUS_CHARS}"
        )
    if len(value) != len(set(value)):
        raise ValidationError("Duplicate characters are not allowed.")


class CancellationRule(models.Model):
    """


    """
    organizer=models.ForeignKey(
        "Organizer",
        related_name="orders",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    event=models.ForeignKey(
        Event,
        verbose_name=_("Event"),
        related_name="orders",
        on_delete=models.CASCADE
    )
    items = models.ManyToManyField(
        "Item",
        verbose_name=_("Items"),
    )
    variations=models.ManyToManyField(
        "ItemVariation",
        verbose_name=_("Item variations"),
    )

    allowed_if_in_order_status=models.CharField(
        max_length=4,
        choices=Order.STATUS_CHOICE,
        verbose_name=_("Cancellation possible if order is in status"),
        validators=[validate_status_chars],
        default="".join(Order.ALLOWED_STATUS_CHARS),
    )
    allowed_until=ModelRelativeDateTimeField(null=True, blank=True)
    except_after=ModelRelativeDateTimeField(null=True, blank=True)

    fee_percentage_per_item=models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MaxValueValidator(
                limit_value=Decimal("100.00"),
            ),
            MinValueValidator(
                limit_value=Decimal("0.00"),
            ),
        ],
        verbose_name=_("Fee Percentage per Item"),
        default=Decimal("0.00"),
    )  # wird als sum() kombiniert
    fee_absolute_per_item=models.DecimalField(
        max_digits=13,
        decimal_places=2,
        verbose_name=_("Absolute Fee per Item"),
        default=Decimal("0.00"),
    )  # wird als sum() kombiniert
    fee_absolute_per_order=models.DecimalField(
        max_digits=13,
        decimal_places=2,
        verbose_name=_("Absolute Fee per Cancellation"),
        default=Decimal("0.00"),
    )  # wird als max() kombiniert

    objects=ScopedManager(CancellationRuleQuerySet.as_manager().__class__, organizer='organizer',
                          event='event')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # erstmal festgelegte List an Stornoregeln, weitere checks können zukünftig über ein
        # Signal eingesammelt und an CancellationRule.__init__ übergeben werden
        # Ermöglicht dann: "Shipping modul kann storno geshippter Items verhindern"
        self.checks: List[CheckFn]=[self._check_order_status, self._check_time_window,
                                    self._system_check_not_checked_in, self._system_check_not_discounted]


    # TODO weitere System Checks
    # OrderPositions mit Item.min_per_order dürfen nur storniert werden, wenn genug übrig bleiben oder alle des gleichen Items storniert werden
    # OrderPositions mit addon_to != None dürfen nur über den bestehenden Add-On-Flow storniert werden
    # OrderPositions mit is_bundled dürfen nur mit der Parent-Position zusammen storniert werden

    @staticmethod
    def _system_check_not_checked_in(diff: OrderDiff, order_position: OrderPosition) -> CheckResult:
        check_id = "SYSTEM_TICKET_NOT_USED"

        if order_position.checkins.filter(list__consider_tickets_used=True).exists():
            return {check_id: CheckRes(
                cancellation_possible=False,
                reason=f"Order position was used",
            )}
        else:
            return {check_id: CheckRes(
                cancellation_possible=True,
                reason=f"Order position not yet used",
            )}

    @staticmethod
    def _system_check_not_discounted(diff: OrderDiff, order_position: OrderPosition) -> CheckResult:
        """
        Check that ensures that orders containing discounted order_positions cannot
        be canceled partially.
        This is a stop-gap solution until the `discount_grouper` attribute for
        AbstractPositions is introduced, allowing us to be more grannular

        :param diff:
        :param order_position:
        :return CheckResults:
        """
        check_id = "SYSTEM_TICKET_NOT_DISCOUNTED"

        if order_position in diff.cancellations():
            if order_position.discount is None:
                return {check_id: CheckRes(
                    cancellation_possible=True,
                    reason=_("Order position was bought without discount"),
                )}
            else:
                return {check_id: CheckRes(
                    cancellation_possible=False,
                    reason=_("Order position was bought with a discount"),
                )}
        else:
            return {check_id: CheckRes(
                cancellation_possible=False,
                reason=_("Order position not canceled - check not applicable"),
            )}

    def _check_time_window(self, diff: OrderDiff, order_position: OrderPosition) -> CheckResult:
        check_id = "TIME_WINDOW"

        if not self.allowed_until and not self.allowed_until:
            return {check_id: CheckRes(
                cancellation_possible=True,
                reason=f"No time window specified",
            )}

        relevant_event=order_position.subevent or order_position.event
        in_allowed_until=time_machine_now() < self.allowed_until.datetime(
                relevant_event) if self.allowed_until else False
        in_exemption=time_machine_now() > self.except_after.datetime(
                relevant_event) if self.except_after else False

        if in_allowed_until and not in_exemption:
            except_after_message = f" and not after {self.except_after.datetime(relevant_event)}" if self.except_after else ""
            return {check_id: CheckRes(
                cancellation_possible=True,
                reason=f"Cancellation in required time window before {self.allowed_until.datetime(relevant_event)}{except_after_message}",
            )}
        elif in_allowed_until and in_exemption:
            return {check_id: CheckRes(
                cancellation_possible=False,
                reason=f"Cancellation in exemption period after {self.except_after.datetime(relevant_event)}",
            )}
        else:
            return {check_id: CheckRes(
                cancellation_possible=False,
                reason=f"Cancellation after time window ending on {self.allowed_until.datetime(relevant_event)}",
            )}


    def _check_order_status(self, diff: OrderDiff, order_position: OrderPosition) -> CheckResult:
        check_id = "ORDER_STATUS"

        if diff.order.status == "".join(Order.ALLOWED_STATUS_CHARS):
            return {check_id: CheckRes(
                cancellation_possible=True,
                reason=f"Orders in every status can be cancelled",
            )}
        elif diff.order.status in self.allowed_if_in_order_status:
            return {check_id: CheckRes(
                cancellation_possible=True,
                reason=f"Order in required status: '{diff.order.status}'",
            )}
        else:
            return {check_id: CheckRes(
                cancellation_possible=False,
                reason=f"Order in status '{diff.order.status}' cannot be canceled",
            )}


    def apply(self, diff: OrderDiff, order_position: OrderPosition) -> Ruling:
        check_results=reduce(merge_check_results,
                       [rule(diff, order_position) for rule in self.checks])

        if self.fee_percentage_per_item and self.fee_absolute_per_item:
            raise NotImplementedError("Should never be reached")
        elif self.fee_absolute_per_item:
            fee=AbsoluteFee(self.fee_absolute_per_item)
        else:
            fee=RelativeFee(percentage=self.fee_percentage_per_item,
                            reference_price=order_position.price)

        return Ruling(
            rule_id=self.id,
            results=check_results,
            order_fee=self.fee_absolute_per_order,
            position_fee=fee
        )
