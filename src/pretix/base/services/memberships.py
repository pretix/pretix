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
from datetime import timedelta
from typing import List, Optional

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from pretix.base.models import (
    AbstractPosition, CartPosition, Customer, Event, Item, Membership, Order,
    OrderPosition, SubEvent,
)
from pretix.base.timemachine import time_machine_now
from pretix.helpers import OF_SELF


def membership_validity(item: Item, subevent: Optional[SubEvent], event: Event):
    tz = event.timezone
    if item.grant_membership_duration_like_event:
        ev = subevent or event
        date_start = ev.date_from
        date_end = ev.date_to

        if not date_end:
            # Use end of day, if event end date is not set
            date_end = date_start.astimezone(tz).replace(hour=23, minute=59, second=59, microsecond=999999)

    else:
        # Always start at start of day
        date_start = time_machine_now().astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_start

        if item.grant_membership_duration_months:
            date_end -= timedelta(days=1)  # start on 25th gives end on 26th
            date_end += relativedelta(months=item.grant_membership_duration_months)  # start on 31th may give end on 28th

        if item.grant_membership_duration_days:
            date_end += timedelta(days=item.grant_membership_duration_days)
            if not item.grant_membership_duration_months:
                # Correct off-by-one due to first day
                date_end -= timedelta(days=1)

        # Always end at end of day
        date_end = date_end.astimezone(tz).replace(hour=23, minute=59, second=59, microsecond=999999)

    return date_start, date_end


def create_membership(customer: Customer, position: OrderPosition):
    item = position.item

    date_start, date_end = membership_validity(item, position.subevent, position.order.event)

    customer.memberships.create(
        membership_type=position.item.grant_membership_type,
        granted_in=position,
        date_start=date_start,
        date_end=date_end,
        attendee_name_parts=position.attendee_name_parts,
        testmode=position.order.testmode,
    )


def validate_memberships_in_order(customer: Customer, positions: List[AbstractPosition], event: Event, lock=False, ignored_order: Order = None, testmode=False,
                                  valid_from_not_chosen=False):
    """
    Validate that a set of cart or order positions. This currently does not validate

    :param customer: Customer to validate for
    :param positions: List of order or cart positions
    :param event: Event this all is computed in
    :param lock: Whether to place a SELECT FOR UPDATE lock on the selected memberships
    :param ignored_order: An order that should be ignored for usage counting
    :param testmode: If ``True``, only test mode memberships are allowed. If ``False``, test mode memberships are not allowed.
    :param valid_from_not_chosen: Set to ``True`` to indicate that the customer is in an early step of the checkout flow
                                  where the valid_from date is not selected yet. In this case, the valid_from date is not checked.
    """
    tz = event.timezone
    applicable_positions = [
        p for p in positions
        if p.item.require_membership or (p.variation and p.variation.require_membership)
    ]

    for p in positions:
        if p not in applicable_positions and p.used_membership_id:
            raise ValidationError(
                _('You selected a membership for the product "{product}" which does not require a membership.').format(
                    product=str(p.item.name) + (' – ' + str(p.variation.value) if p.variation else '')
                )
            )

    for p in applicable_positions:
        if not p.used_membership_id:
            raise ValidationError(
                _('You selected the product "{product}" which requires an active membership to '
                  'be selected.').format(
                    product=str(p.item.name) + (' – ' + str(p.variation.value) if p.variation else '')
                )
            )

    base_qs = Membership.objects.with_usages(ignored_order=ignored_order)

    if lock:
        base_qs = base_qs.select_for_update(of=OF_SELF)

    membership_cache = base_qs\
        .select_related('membership_type')\
        .prefetch_related('orderposition_set', 'orderposition_set__order', 'orderposition_set__order__event', 'orderposition_set__subevent')\
        .in_bulk([p.used_membership_id for p in applicable_positions])

    for m in membership_cache.values():
        qs = m.orderposition_set.filter(canceled=False).exclude(order__status=Order.STATUS_CANCELED)
        if ignored_order:
            qs = qs.exclude(order_id=ignored_order.pk)
        m._used_at_dates = [
            (op.subevent or op.order.event).date_from
            for op in qs if not op.valid_from or not op.valid_until
        ]
        m._used_for_ranges = [
            (op.valid_from, op.valid_until)
            for op in qs if op.valid_from or op.valid_until
        ]

    for p in applicable_positions:
        m = membership_cache[p.used_membership_id]
        if not customer or m.customer_id != customer.pk:
            raise ValidationError(
                _('You selected a membership that is connected to a different customer account.')
            )

        if m.canceled:
            raise ValidationError(
                _('You selected membership that has been canceled.')
            )

        if m.testmode and not testmode:
            raise ValidationError(
                _('You can not use a test mode membership for tickets that are not in test mode.')
            )
        elif not m.testmode and testmode:
            raise ValidationError(
                _('You need to add a test mode membership to the customer account to use it in test mode.')
            )

        ev = p.subevent or event

        if isinstance(p, (OrderPosition, CartPosition)):
            # override_ variants are for usage of fake cart in OrderChangeManager
            valid_from = getattr(p, 'override_valid_from', p.valid_from)
            valid_until = getattr(p, 'override_valid_until', p.valid_until)
        else:  # future safety, not technically defined on AbstractPosition
            valid_from = None
            valid_until = None

        if not m.is_valid(ev, valid_from, valid_from_not_chosen=p.item.validity_dynamic_start_choice and valid_from_not_chosen):
            if valid_from:
                raise ValidationError(
                    _('You selected a membership that is valid from {start} to {end}, but selected a ticket that '
                      'starts to be valid on {date}.').format(
                        start=date_format(m.date_start.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                        end=date_format(m.date_end.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                        date=date_format(valid_from.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                    )
                )
            else:
                raise ValidationError(
                    _('You selected a membership that is valid from {start} to {end}, but selected an event '
                      'taking place at {date}.').format(
                        start=date_format(m.date_start.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                        end=date_format(m.date_end.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                        date=date_format(ev.date_from.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                    )
                )

        if p.variation and p.variation.require_membership:
            types = p.variation.require_membership_types.all()
        else:
            types = p.item.require_membership_types.all()

        if not types.filter(pk=m.membership_type_id).exists():
            raise ValidationError(
                _('You selected a membership of type "{type}", which is not allowed for the product "{product}".').format(
                    product=str(p.item.name) + (' – ' + str(p.variation.value) if p.variation else ''),
                    type=m.membership_type.name
                )
            )

        if m.membership_type.max_usages is not None:
            if m.usages >= m.membership_type.max_usages:
                raise ValidationError(
                    _('You are trying to use a membership of type "{type}" more than {number} times, which is the maximum amount.').format(
                        type=m.membership_type.name,
                        number=m.usages,
                    )
                )
            m.usages += 1

        if not m.membership_type.allow_parallel_usage:
            if (valid_from or valid_until) and not (p.item.validity_dynamic_start_choice and valid_from_not_chosen):
                for used_range in m._used_for_ranges:
                    if valid_from and valid_from > used_range[1]:
                        continue
                    if valid_until and valid_until < used_range[0]:
                        continue
                    raise ValidationError(
                        _('You are trying to use a membership of type "{type}" for a ticket valid from {valid_from} '
                          'until {valid_until}, however you already used the same membership for a different ticket '
                          'that overlaps with this time frame ({conflict_from} – {conflict_until}).').format(
                            type=m.membership_type.name,
                            valid_from=date_format(valid_from.astimezone(tz), 'SHORT_DATETIME_FORMAT') if valid_from else _('start'),
                            valid_until=date_format(valid_until.astimezone(tz), 'SHORT_DATETIME_FORMAT') if valid_until else _('open end'),
                            conflict_from=date_format(used_range[0].astimezone(tz), 'SHORT_DATETIME_FORMAT') if used_range[0] else _('start'),
                            conflict_until=date_format(used_range[1].astimezone(tz), 'SHORT_DATETIME_FORMAT') if used_range[1] else _('open end'),
                        )
                    )

                m._used_for_ranges.append((p.valid_from, p.valid_until))

            if not valid_from or not valid_until:
                df = ev.date_from
                if any(abs(df - d) < timedelta(minutes=1) for d in m._used_at_dates):
                    raise ValidationError(
                        _('You are trying to use a membership of type "{type}" for an event taking place at {date}, '
                          'however you already used the same membership for a different ticket at the same time.').format(
                            type=m.membership_type.name,
                            date=date_format(ev.date_from.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                        )
                    )
                m._used_at_dates.append(ev.date_from)
