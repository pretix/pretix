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
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from itertools import chain
from typing import (
    TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple, cast,
)

from django.core.exceptions import ValidationError
from django.db.models import Prefetch, QuerySet
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from pretix.base.cancellation import (
    CancellationCheck, CancellationResult, CheckResult, CheckTypes,
    PositionResult, PositionSet, ProcessResult, RuleResult,
)
from pretix.base.models import Event, Membership, Order, OrderPosition
from pretix.base.models.cancellation import (
    Cancellation, PositionCancellationRule, ProcessCancellationRule,
)
from pretix.base.signals import self_service_cancellation_checks

if TYPE_CHECKING:
    from pretix.base.cancellation import PrefetchedOrder, PrefetchedPosition


@dataclass(frozen=True)
class CollectedChecks:
    position: List[CancellationCheck]
    process: List[CancellationCheck]

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


def evaluate_cancellation(event: Event, order: Order, keep: Set[OrderPosition],
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
    collected_checks = collect_cancellation_checks(event=event)
    position_rules: QuerySet[PositionCancellationRule] = PositionCancellationRule.objects.filter(
        event=event).with_rule_data().all()
    process_rules: QuerySet[ProcessCancellationRule] = ProcessCancellationRule.objects.filter(
        event=event).with_rule_data().all()

    order = _prefetch_order(event, order, collected_checks)

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
        for check in collected_checks.position:
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
    for check in collected_checks.process:
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


def prepare_cancellation(event: Event, order: Order, keep: Set[OrderPosition],
                         check_ts: datetime.datetime) -> Cancellation:
    res = evaluate_cancellation(event=event, order=order, keep=set(), check_ts=check_ts)
    c = Cancellation(event=event, order=order, result=res, evaluation_ts=check_ts)
    c.save()
    c.keep.add(*keep)
    return c


def perform_cancellation(cancellation: Cancellation):
    # TODO load the cancellation verdict and perform the actions via the OCM
    pass


def _send_self_service_cancellation_checks(event: Event) -> List[Tuple[Any, Any]]:
    return self_service_cancellation_checks.send(sender=event)


def collect_cancellation_checks(event: Event, send_fn: Callable[
    [Event], List[Tuple[Any, Any]]
] = _send_self_service_cancellation_checks) -> CollectedChecks:
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

    return CollectedChecks(position=position_checks, process=process_checks)


def _prefetch_order(event: Event, order: Order, checks: CollectedChecks) -> "PrefetchedOrder":
    prefetches = [pref() for pref in
                  [*checks.prefetches, *PositionCancellationRule.prefetches, *ProcessCancellationRule.prefetches]]

    related_selects = {*checks.related_selects,
                       *PositionCancellationRule.related_selects,
                       *ProcessCancellationRule.related_selects}

    qs = Order.objects.prefetch_related(*prefetches)
    if related_selects:
        qs = qs.select_related(*related_selects)

    return cast("PrefetchedOrder", qs.get(event=event, id=order.id))


def position_not_used_cancellation_check(order: "PrefetchedOrder", keep: PositionSet, position: "PrefetchedPosition",
                                         check_ts: datetime.datetime) -> Optional[CheckResult]:
    if position in keep:
        return None

    used_checkin = next(
        (c for c in position.all_checkins.all() if
         c.successful and c.list.consider_tickets_used and c.datetime < check_ts),
        None,
    )
    if used_checkin is not None:
        return CheckResult(
            id="pretixbase_position_not_used",
            reason=_("Ticket has already been checked in on list {list}").format(list=used_checkin.list.name),
            cancellation_possible=False,
        )
    return CheckResult(
        id="pretixbase_position_not_used",
        reason=_("Ticket has not been used"),
        cancellation_possible=True,
    )


@receiver(self_service_cancellation_checks, dispatch_uid="pretixbase_position_not_used")
def signal_listener_position_not_used(sender: Event, **kwargs) -> CancellationCheck:
    return CancellationCheck(id="pretixbase_position_not_used",
                             type=CheckTypes.POSITION,
                             check_fn=position_not_used_cancellation_check,
                             prefetches=[
                                 lambda: Prefetch('all_positions__all_checkins__list', )
                             ])


def position_not_blocked_check(order: Order, keep: PositionSet, position: OrderPosition,
                               check_ts: datetime.datetime) -> Optional[CheckResult]:
    if position in keep:
        return None

    return CheckResult(
        id="pretixbase_position_not_blocked",
        reason=_("Position is blocked") if position.blocked else _("Position is not blocked"),
        cancellation_possible=not position.blocked,
    )


@receiver(self_service_cancellation_checks, dispatch_uid="pretixbase_position_not_blocked")
def signal_listener_position_not_blocked(sender: Event, **kwargs) -> CancellationCheck:
    return CancellationCheck(id="pretixbase_position_not_blocked",
                             type=CheckTypes.POSITION,
                             check_fn=position_not_blocked_check,
                             prefetches=[
                                 lambda: Prefetch('all_positions', )
                             ])


def position_giftcard_not_used(order: PrefetchedOrder, keep: PositionSet, position: PrefetchedPosition,
                               check_ts: datetime.datetime) -> Optional[CheckResult]:
    if position in keep:
        return None

    if len(position.issued_gift_cards.all()) > 0:
        for gc in position.issued_gift_cards.all():
            if gc.value != position.price:
                return CheckResult(
                    id="pretixbase_position_giftcard_not_used",
                    reason=_("Issued giftcard was used"),
                    cancellation_possible=False,
                )
        return CheckResult(
            id="pretixbase_position_giftcard_not_used",
            reason=_("Issued giftcard was not used"),
            cancellation_possible=True,
        )
    return None


@receiver(self_service_cancellation_checks, dispatch_uid="pretixbase_position_giftcard_not_used")
def signal_listener_position_giftcard_not_used(sender: Event, **kwargs) -> CancellationCheck:
    return CancellationCheck(id="pretixbase_position_giftcard_not_used",
                             type=CheckTypes.POSITION,
                             check_fn=position_giftcard_not_used,
                             prefetches=[
                                 lambda: Prefetch('all_positions__issued_gift_cards', )
                             ])


def position_membership_not_used(order: PrefetchedOrder, keep: PositionSet, position: PrefetchedPosition,
                                 check_ts: datetime.datetime) -> Optional[CheckResult]:
    if position in keep:
        return None

    if len(position.granted_memberships.all()) > 0:
        for membership in position.granted_memberships.all():
            if membership.usages > 0:
                return CheckResult(
                    id="pretixbase_position_membership_not_used",
                    reason=_("Membership was already used"),
                    cancellation_possible=False,
                )

        return CheckResult(
            id="pretixbase_position_membership_not_used",
            reason=_("Included Memberships were not used"),
            cancellation_possible=True,
        )

    return None


@receiver(self_service_cancellation_checks, dispatch_uid="pretixbase_position_membership_not_used")
def signal_position_membership_not_used(sender: Event, **kwargs) -> CancellationCheck:
    return CancellationCheck(id="pretixbase_position_membership_not_used",
                             type=CheckTypes.POSITION,
                             check_fn=position_membership_not_used,
                             prefetches=[
                                 lambda: Prefetch('all_positions__granted_memberships',
                                                  queryset=Membership.objects.with_usages(), )
                             ])


def position_item_allow_cancel(order: PrefetchedOrder, keep: PositionSet, position: PrefetchedPosition,
                               check_ts: datetime.datetime) -> Optional[CheckResult]:
    if position in keep:
        return None

    return CheckResult(
        id="pretixbase_position_item_allow_cancel",
        reason=_("Item can be canceled") if position.item.allow_cancel else _("Item cannot be canceled"),
        cancellation_possible=position.item.allow_cancel,
    )


@receiver(self_service_cancellation_checks, dispatch_uid="pretixbase_position_item_allow_cancel")
def signal_position_item_allow_cancel(sender: Event, **kwargs) -> CancellationCheck:
    return CancellationCheck(id="pretixbase_position_item_allow_cancel",
                             type=CheckTypes.POSITION,
                             check_fn=position_item_allow_cancel,
                             prefetches=[
                                 lambda: Prefetch('all_positions__item')
                             ])


def process_order_payment_state(order: PrefetchedOrder, keep: PositionSet, check_ts: datetime.datetime):
    if order.status == Order.STATUS_PAID:
        if order.total == Decimal("0.00"):
            return CheckResult(
                id="pretixbase_process_order_paid",
                reason=_(
                    "Free orders can be canceled") if order.event.settings.cancel_allow_user else _(
                    "Free orders cannot be canceled"),
                cancellation_possible=order.event.settings.cancel_allow_user,
            )
        return CheckResult(
            id="pretixbase_process_order_paid",
            reason=_("Paid orders can be canceled") if order.event.settings.cancel_allow_user_paid else _(
                "Paid orders cannot be canceled"),
            cancellation_possible=order.event.settings.cancel_allow_user_paid,
        )
    elif order.payment_refund_sum > Decimal('0.00'):
        return CheckResult(
            id="pretixbase_process_order_paid",
            reason=_("Outstanding refund sum prevents further cancellations"),
            cancellation_possible=False,
        )
    elif order.status == Order.STATUS_PENDING:
        return CheckResult(
            id="pretixbase_process_order_paid",
            reason=_("Pending orders can be canceled") if order.event.settings.cancel_allow_user else _(
                "Pending orders cannot be canceled"),
            cancellation_possible=order.event.settings.cancel_allow_user,
        )
    else:
        return CheckResult(
            id="pretixbase_process_order_paid",
            reason=_("Order is in a state that does not allow cancellations"),
            cancellation_possible=False,
        )


@receiver(self_service_cancellation_checks, dispatch_uid="pretixbase_process_order_payment_state")
def signal_listener_process_order_payment_state(sender: Event, **kwargs) -> CancellationCheck:
    return CancellationCheck(id="pretixbase_process_order_payment_state",
                             type=CheckTypes.PROCESS,
                             check_fn=process_order_payment_state,
                             prefetches=[]
                             )


def process_cancel_allowed(order: PrefetchedOrder, keep: PositionSet, check_ts: datetime.datetime) -> CheckResult:
    cancel_allowed = order.cancel_allowed()

    return CheckResult(
        id="pretixbase_process_cancel_allowed",
        reason=_("Order allows cancellation") if cancel_allowed else _("Order doesn't allow for cancellation"),
        cancellation_possible=cancel_allowed,
    )


@receiver(self_service_cancellation_checks, dispatch_uid="pretixbase_process_cancel_allowed")
def signal_listener_process_cancel_allowed(sender: Event, **kwargs) -> CancellationCheck:
    return CancellationCheck(id="pretixbase_process_process_cancel_allowed",
                             type=CheckTypes.PROCESS,
                             check_fn=process_cancel_allowed,
                             prefetches=[]
                             )


def process_cancellation_in_progress(order: PrefetchedOrder, keep: PositionSet, check_ts: datetime.datetime):
    if any([c.state not in [Cancellation.STATE_PERFORMED, Cancellation.STATE_ABORTED] for c in
            order.cancellations.all()]):
        return CheckResult(
            id="pretixbase_process_cancellation_in_progress",
            reason=_("Cancellation request already in progress"),
            cancellation_possible=False,
        )

    return CheckResult(
        id="pretixbase_process_cancellation_in_progress",
        reason=_("No cancellation request in progress"),
        cancellation_possible=True,
    )


@receiver(self_service_cancellation_checks, dispatch_uid="pretixbase_process_cancellation_in_progress")
def signal_listener_process_cancellation_in_progress(sender: Event, **kwargs) -> CancellationCheck:
    return CancellationCheck(id="pretixbase_process_process_cancellation_in_progress",
                             type=CheckTypes.PROCESS,
                             check_fn=process_cancellation_in_progress,
                             prefetches=[]
                             )

# TODO weitere System Checks
# OrderPositions mit Item.min_per_order dürfen nur storniert werden, wenn genug übrig bleiben oder alle des gleichen Items storniert werden
# OrderPositions mit addon_to != None dürfen nur über den bestehenden Add-On-Flow storniert werden
# OrderPositions mit is_bundled dürfen nur mit der Parent-Position zusammen storniert werden
