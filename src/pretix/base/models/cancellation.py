import dataclasses
from dataclasses import dataclass
from decimal import Decimal
from functools import reduce
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.db import models
from django_scopes import ScopedManager

from pretix.base.models import Event
from pretix.base.models import OrderPosition, Order
from typing import Dict, Union, Callable, List

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
        return self.reference_price * self.percentage


@dataclass(frozen=True)
class Ruling:
    cancellation_possible: bool
    reason: str


Rulings=Dict[str, Ruling]
Fee=Union[AbsoluteFee, RelativeFee]
RuleFn=Callable[[OrderPosition], Rulings]


def merge_rulings(a: Rulings, b: Rulings) -> Rulings:
    result = dict(a)
    for key, b_inner in b.items():
        if key in result:
            result[key] = result[key] | b_inner  # merge inner dicts
        else:
            result[key] = b_inner
    return result

@dataclass(frozen=True)
class CancellationConsequence:
    rule_id: int
    rulings: Rulings
    order_fee: Decimal=dataclasses.field(default_factory=lambda: Decimal(0))
    position_fee: Fee=dataclasses.field(default_factory=lambda: AbsoluteFee(Decimal(0)))

    cancellation_possible: bool=dataclasses.field(init=False)

    def __post_init__(self):
        object.__setattr__(
            self,
            'cancellation_possible',
            all(ruling.cancellation_possible
                for ruling in self.rulings.values()
            )
        )

    @property
    def total_fee(self):
        return self.position_fee.amount + self.order_fee

    def __lt__(self, other):
        if not isinstance(other, CancellationConsequence):
            return NotImplemented

        if self.cancellation_possible == other.cancellation_possible:
            return self.total_fee < other.total_fee
        else:
            return self.cancellation_possible and not other.cancellation_possible


class CancellationRuleQuerySet(models.QuerySet):
    def cancellation_possible(self, order: Order):
        return all([v[0].cancellation_possible for v in self._evaluate(order)])

    def _evaluate(self, order: Order) -> List[List[CancellationConsequence]]:
        return [self._evaluate_op(position) for position in order.positions.all()]

    def _evaluate_op(self, order_position: OrderPosition) -> List[CancellationConsequence]:
        consequences=[rule.apply(order_position) for rule in self]
        consequences.sort()
        return consequences



class CancellationRule(models.Model):
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
    item=models.ForeignKey("Item", on_delete=models.CASCADE, null=True, blank=True)
    item_variation=models.ForeignKey("ItemVariation", on_delete=models.CASCADE, null=True, blank=True)

    order_status=models.CharField(
        max_length=3,
        choices=Order.STATUS_CHOICE,
        verbose_name=_("Status"),
        db_index=True
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
        self.rules: List[RuleFn]=[self._rule_order_status, self._rule_time_window,
                                  self._system_rule_not_checked_in]

    @staticmethod
    def _system_rule_not_checked_in(order_position: OrderPosition) -> Rulings:
        if order_position.checkins.filter(list__consider_tickets_used=True).exists():
            return {"SYSTEM_TICKET_NOT_USED": Ruling(
                cancellation_possible=False,
                reason=f"Order position was used",
            )}
        else:
            return {"SYSTEM_TICKET_NOT_USED": Ruling(
                cancellation_possible=True,
                reason=f"Order position not yet used",
            )}

    def _rule_time_window(self, order_position: OrderPosition) -> Rulings:
        in_allowed_until = self.allowed_until < time_machine_now()
        in_exemption = self.except_after > time_machine_now()
        if in_allowed_until and not in_exemption:
            return {"TIME_WINDOW": Ruling(
                cancellation_possible=True,
                reason=f"Cancellation in required time window between {self.allowed_until} and {self.except_after}",
            )}
        elif in_allowed_until and in_exemption:
            return {"TIME_WINDOW": Ruling(
                cancellation_possible=False,
                reason=f"Cancellation in exemption period after {self.except_after}",
            )}
        else:
            return {"TIME_WINDOW": Ruling(
                cancellation_possible=False,
                reason=f"Cancellation after time window ending on {self.allowed_until}",
            )}

    def _rule_order_status(self, order_position: OrderPosition) -> Rulings:
        if order_position.order.status == self.order_status:
            return {"ORDER_STATUS": Ruling(
                cancellation_possible=True,
                reason=f"Order in required status: '{order_position.order.status}'",
            )}
        else:
            return {"ORDER_STATUS": Ruling(
                cancellation_possible=False,
                reason=f"Order in status '{order_position.order.status}' cannot be canceled",
            )}

    # OrderPositions mit discount dürfen nur storniert werden, wenn alle positions mit dem gleichen discount_grouper storniert werden
    # OrderPositions mit Item.min_per_order dürfen nur storniert werden, wenn genug übrig bleiben oder alle des gleichen Items storniert werden
    # OrderPositions mit addon_to != None dürfen nur über den bestehenden Add-On-Flow storniert werden
    # OrderPositions mit is_bundled dürfen nur mit der Parent-Position zusammen storniert werden
    # Shipping modul kann storno geshippter Items verhindern
    # Backend-Anzeige "welche Regel greift da gerade" in der Order

    def apply(self, order_position: OrderPosition) -> CancellationConsequence:
        rulings=reduce(merge_rulings,
                       [rule(order_position) for rule in self.rules])

        if self.fee_percentage_per_item and self.fee_absolute_per_item:
            raise NotImplementedError("Should never be reached")
        elif self.fee_absolute_per_item:
            fee=AbsoluteFee(self.fee_absolute_per_item)
        else:
            fee=RelativeFee(percentage=self.fee_absolute_per_item,
                            reference_price=order_position.price)

        return CancellationConsequence(
            rule_id=self.id,
            rulings=rulings,
            order_fee=self.fee_absolute_per_order,
            position_fee=fee
        )
