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
    Set,
)

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Prefetch
from django.utils.timezone import make_aware
from django.utils.translation import gettext_lazy as _

from pretix.base.cancellation import (
    CancellationResult, CheckResult, CheckTypes, FeeType, RuleResult,
)
from pretix.base.models import Event, Item, ItemVariation, Order, OrderPosition
from pretix.base.reldate import ModelRelativeDateTimeField, RelativeDateWrapper
from pretix.helpers import ensure_no_queries


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
