#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import datetime
import operator
from dataclasses import asdict
from decimal import Decimal
from typing import (
    TYPE_CHECKING, Any, Callable, ClassVar, Final, List, Literal, Optional,
    Set, Union,
)

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Prefetch
from django.utils.functional import Promise
from django.utils.timezone import make_aware
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.cancellation import (
    CancellationResult, CheckResult, CheckTypes, FeeType, RuleResult,
)
from pretix.base.reldate import ModelRelativeDateTimeField, RelativeDateWrapper
from pretix.base.templatetags.money import money_filter
from pretix.helpers import ensure_no_queries

from pretix.base.models import LoggedModel

if TYPE_CHECKING:
    from pretix.base.models import Order, OrderPosition


class CancellationRequest(models.Model):
    STATE_CREATED: Final = "created"
    STATE_PENDING: Final = "pending"
    STATE_PERFORMED: Final = "performed"
    STATE_DENIED: Final = "denied"

    CANCELLATION_CHOICES = (
        (STATE_CREATED, _("Created")),
        (STATE_PENDING, _("Pending")),
        (STATE_PERFORMED, _("Performed")),
        (STATE_DENIED, _("Denied")),
    )

    event = models.ForeignKey(
        "Event",
        verbose_name=_("Event"),
        related_name="cancellation_requests",
        on_delete=models.CASCADE
    )
    order = models.ForeignKey(
        "Order",
        verbose_name=_("Order"),
        related_name="cancellation_requests",
        on_delete=models.CASCADE
    )
    created = models.DateTimeField(auto_now_add=True)

    keep = models.ManyToManyField(
        to="OrderPosition",
        verbose_name=_("Positions to keep"),
    )
    evaluated_at = models.DateTimeField(
        verbose_name=_("Cancellation datetime"),
    )
    cancellation_fee = models.DecimalField(max_digits=13, decimal_places=2)
    refund_as_giftcard = models.BooleanField(default=False)
    state = models.CharField(
        max_length=16,
        choices=CANCELLATION_CHOICES,
        default=STATE_CREATED,
        verbose_name=_("State of the cancellation"),
    )

    _result = models.JSONField(default=dict, db_column="result", encoder=DjangoJSONEncoder)

    def deny(self, user):
        with transaction.atomic():
            self.state = CancellationRequest.STATE_DENIED
            self.order.log_action('pretix.event.order.cancellationrequest.denied', {
            }, user=user)
            self.save(update_fields=['state'])

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
        return super().get_queryset().order_by("pk")


CancellationVariant = Literal["earliest", "latest"]


class CancellationRule(LoggedModel):
    VARIANT_EARLIEST: Final = "earliest"
    VARIANT_LATEST: Final = "latest"

    SUBEVENT_VARIANT_CHOICES = (
        (VARIANT_EARLIEST, _("Earliest")),
        (VARIANT_LATEST, _("Latest")),
    )

    internal_name = models.CharField(
        verbose_name=_('Internal name'),
        max_length=190,
    )

    allowed_until = ModelRelativeDateTimeField(null=True, blank=True, verbose_name=_("Allowed until"))
    except_after = ModelRelativeDateTimeField(null=True, blank=True, verbose_name=_("Except after"))
    if TYPE_CHECKING:
        allowed_until: Optional[RelativeDateWrapper]
        except_after: Optional[RelativeDateWrapper]

    subevent_variant = models.CharField(
        max_length=8,
        choices=SUBEVENT_VARIANT_CHOICES,
        default=VARIANT_EARLIEST,
        verbose_name=pgettext_lazy("subevent", "Multiple date handling"),
        help_text=pgettext_lazy("subevent", "An order can contain order positions for multiple different dates."
                                            "This choice controls if the order position for the earliest "
                                            "or the latest date in the order is used to determine the allowed until and "
                                            "except after dates.")
    )

    class Meta:
        abstract = True

    @staticmethod
    def _resolve_date_field_common(
            date_field: RelativeDateWrapper,
            order: "Order",
            resolve_subevent: Callable[[Any], Any],
    ) -> Union[datetime.date, datetime.datetime]:
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


limit_names = {
    'allowed_until': _("allowed-until"),
    'except_after': _("except-after"),
}


class PositionCancellationRule(CancellationRule):
    """
    PositionCancellationRules answer the questions:
    - Can this position be canceled?
    - What is the price for cancelling this position?
    """
    ruletype = "position"

    objects = CancellationRuleManager()

    event = models.ForeignKey(
        "Event",
        verbose_name=_("Event"),
        related_name="position_cancellation_rules",
        on_delete=models.CASCADE
    )

    fee_percentage_per_position = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
        verbose_name=_("Fee percentage per order position"),
        default=Decimal("0.00"),
    )
    fee_absolute_per_position = models.DecimalField(
        max_digits=13,
        decimal_places=2,
        verbose_name=_("Absolute fee per order position"),
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    all_products = models.BooleanField(
        verbose_name=_("All products and variations"),
        default=True,
    )
    limit_products = models.ManyToManyField("Item", verbose_name=_("Products"), blank=True)
    limit_variations = models.ManyToManyField(
        "ItemVariation", blank=True, verbose_name=_("Variations")
    )

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

    @property
    def display_fee(self) -> str | Promise:
        if self.fee_absolute_per_position == Decimal("0.00") and self.fee_absolute_per_position == Decimal("0.00"):
            return _("No fee")
        if self.fee_absolute_per_position != Decimal("0.00"):
            return money_filter(self.fee_absolute_per_position, self.event.currency)
        else:
            return _("{percentage} %").format(percentage=self.fee_absolute_per_position)

    def _position_matches_rule(self, position: "OrderPosition") -> Optional[CheckResult]:
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
    def _resolve_date_field(date_field: RelativeDateWrapper, order: "Order",
                            position: "OrderPosition") -> Union[datetime.date, datetime.datetime]:
        return CancellationRule._resolve_date_field_common(
            date_field, order, resolve_subevent=lambda _reldate_type: position.subevent
        )

    def _evaluate_cancellation_moment(self, position: "OrderPosition", check_at: datetime.datetime) \
            -> List[CheckResult]:
        check_results = []

        order = position.order

        for limit_name in ('allowed_until', 'except_after'):
            deadline: Optional[RelativeDateWrapper] = getattr(self, limit_name, None)
            if deadline is not None:
                deadline_value = self._resolve_date_field(deadline, order, self.subevent_variant)
                if check_at <= deadline_value:
                    check_results.append(
                        CheckResult(
                            id=f"position_rule_{self.id}_{limit_name}",
                            reason=_("{evaluated_at} is earlier than {limit_name} deadline {deadline}").format(
                                evaluated_at=check_at,
                                limit_name=limit_names[limit_name],
                                deadline=deadline_value,
                            ),
                            cancellation_possible=True
                        )
                    )
                else:
                    check_results.append(
                        CheckResult(
                            id=f"position_rule_{self.id}_{limit_name}",
                            reason=_("{evaluated_at} is later than {limit_name} deadline {deadline}").format(
                                evaluated_at=check_at,
                                limit_name=limit_names[limit_name],
                                deadline=deadline_value,
                            ),
                            cancellation_possible=False
                        )
                    )
            else:
                check_results.append(
                    CheckResult(
                        id=f"position_rule_{self.id}_{limit_name}",
                        reason=_("No {limit_name} limit defined").format(limit_name=limit_names[limit_name]),
                        cancellation_possible=True
                    )
                )

        return check_results

    def evaluate_position_rule(self, order: "Order", _keep: Set["OrderPosition"], position: "OrderPosition",
                               check_at: datetime.datetime) -> Optional[RuleResult]:
        rule_check_results = []
        match = self._position_matches_rule(position)
        if match:
            rule_check_results.append(match)
        rule_check_results.extend(self._evaluate_cancellation_moment(position, check_at))

        if self.fee_percentage_per_position and self.fee_absolute_per_position:
            raise NotImplementedError(
                "Combination of fee_percentage_per position and fee_absolute_per_position is not valid")
        elif self.fee_absolute_per_position != Decimal("0"):
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


class ProcessCancellationRule(CancellationRule):
    """
    ProcessCancellationRules answer the question:
    - What is the processing fee for performing this cancellation?
    """
    ruletype = "process"

    objects = CancellationRuleManager()

    event = models.ForeignKey(
        "Event",
        verbose_name=_("Event"),
        related_name="process_cancellation_rules",
        on_delete=models.CASCADE
    )

    fee_cancellation_process = models.DecimalField(
        max_digits=13,
        decimal_places=2,
        verbose_name=_("Absolute fee per cancellation"),
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    fee_mode = models.CharField(
        verbose_name=_("The method with which process and position fees are combined."),
        help_text=_("Process fees can either be used to set the minimum cancellation fee that is charged or "
                    "they can be charged in addition to all position fees."),
        choices=[
            (FeeType.MINIMUM, FeeType.MINIMUM.label),
            (FeeType.ADDITIONAL, FeeType.ADDITIONAL.label),
        ],
        blank=False,
        null=False,
        default=FeeType.MINIMUM,
        max_length=15,
    )

    rule_prefetches: ClassVar[List[Callable[[], Prefetch]]] = []
    rule_related_selects: ClassVar[List[str]] = []

    prefetches: ClassVar[List[Callable[[], Prefetch]]] = [
        lambda: Prefetch('event'),
    ]
    related_selects: ClassVar[List[str]] = []

    @property
    def display_fee(self) -> str | Promise:
        fee_amount = money_filter(self.fee_cancellation_process, self.event.currency)
        if self.fee_mode == FeeType.MINIMUM:
            return _("Position fees or minimum of {fee}").format(fee=fee_amount)
        else:
            return _("Position fees plus {fee}").format(fee=fee_amount)

    @staticmethod
    def _resolve_date_field(date_field: RelativeDateWrapper, order: "Order",
                            mode: CancellationVariant) -> Union[datetime.date, datetime.datetime]:
        if mode not in (CancellationRule.VARIANT_EARLIEST, CancellationRule.VARIANT_LATEST):
            raise ValidationError('Mode is invalid')

        comparators = {
            CancellationRule.VARIANT_EARLIEST: operator.lt,
            CancellationRule.VARIANT_LATEST: operator.gt,
        }
        compare = comparators[mode]

        def resolve_subevent(reldate_type):
            base_event = order.event
            base_value: Optional[datetime.date] = None
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

    def _evaluate_cancellation_moment(self, order: "Order", check_at: datetime.datetime) -> List[CheckResult]:

        check_results: List[CheckResult] = []

        for limit_name in ('allowed_until', 'except_after'):
            deadline: Optional[RelativeDateWrapper] = getattr(self, limit_name, None)
            if deadline is not None:
                deadline_value = self._resolve_date_field(deadline, order, self.subevent_variant)
                if check_at <= deadline_value:
                    check_results.append(
                        CheckResult(
                            id=f"process_rule_{self.id}_{limit_name}",
                            reason=_("{evaluated_at} is earlier than {limit_name} deadline {deadline}").format(
                                evaluated_at=check_at,
                                limit_name=limit_names[limit_name],
                                deadline=deadline_value),
                            cancellation_possible=True
                        )
                    )
                else:
                    check_results.append(
                        CheckResult(
                            id=f"process_rule_{self.id}_{limit_name}",
                            reason=_("{evaluated_at} is later than {limit_name} deadline {deadline}").format(
                                evaluated_at=check_at,
                                limit_name=limit_names[limit_name],
                                deadline=deadline_value),
                            cancellation_possible=False
                        )
                    )
            else:
                check_results.append(
                    CheckResult(
                        id=f"process_rule_{self.id}_{limit_name}",
                        reason=_("No {limit_name} limit defined").format(limit_name=limit_name),
                        cancellation_possible=True
                    )
                )
        return check_results

    def evaluate_process_rule(self, order: "Order", _keep: Set["OrderPosition"], position_fees: Decimal,
                              check_at: datetime.datetime) -> Optional[RuleResult]:
        fee_mode = self.fee_mode
        if fee_mode not in (FeeType.MINIMUM, FeeType.ADDITIONAL):
            raise ValueError(f"Unexpected fee_mode: {fee_mode!r}")

        check_results: List[CheckResult] = self._evaluate_cancellation_moment(order, check_at)

        return RuleResult.from_process_fee(
            id=self.id,
            partial_results=check_results,
            fee_type=fee_mode,
            absolute_fee=self.fee_cancellation_process,
            reference_price=position_fees,
        )
