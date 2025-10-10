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
import copy

from django.db.models import Q
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from pretix.base.models import Checkin, OrderPayment
from pretix.base.signals import (
    checkin_created, event_copy_data, item_copy_data, logentry_display,
    order_paid, order_placed,
)
from pretix.control.signals import nav_event
from pretix.plugins.autocheckin.models import AutoCheckinRule


@receiver(nav_event, dispatch_uid="autocheckin_nav_event")
def nav_event_receiver(sender, request, **kwargs):
    url = request.resolver_match
    if not request.user.has_event_permission(
        request.organizer, request.event, "can_change_event_settings", request=request
    ):
        return []
    return [
        {
            "label": _("Auto check-in"),
            "url": reverse(
                "plugins:autocheckin:index",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.organizer.slug,
                },
            ),
            "parent": reverse(
                "control:event.orders.checkinlists",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.event.organizer.slug,
                },
            ),
            "active": url.namespace == "plugins:autocheckin",
        }
    ]


@receiver(signal=logentry_display)
def logentry_display_receiver(sender, logentry, **kwargs):
    plains = {
        "pretix.plugins.autocheckin.rule.added": _("An auto check-in rule was created"),
        "pretix.plugins.autocheckin.rule.changed": _(
            "An auto check-in rule was updated"
        ),
        "pretix.plugins.autocheckin.rule.deleted": _(
            "An auto check-in rule was deleted"
        ),
    }
    if logentry.action_type in plains:
        return plains[logentry.action_type]


@receiver(item_copy_data, dispatch_uid="autocheckin_item_copy")
def item_copy_data_receiver(sender, source, target, **kwargs):
    for acr in AutoCheckinRule.objects.filter(limit_products=source):
        acr.limit_products.add(target)


@receiver(signal=event_copy_data, dispatch_uid="autocheckin_copy_data")
def event_copy_data_receiver(
    sender, other, item_map, variation_map, checkin_list_map, **kwargs
):
    for acr in other.autocheckinrule_set.all():
        if acr.list and acr.list.subevent:
            continue  # Impossible to copy

        oldacr = acr

        acr = copy.copy(acr)
        acr.pk = None
        acr.event = sender

        if acr.list_id:
            acr.list = checkin_list_map[acr.list_id]

        acr.save()

        if not acr.all_sales_channels:
            acr.limit_sales_channels.set(
                sender.organizer.sales_channels.filter(
                    identifier__in=oldacr.limit_sales_channels.values_list(
                        "identifier", flat=True
                    )
                )
            )

        if not acr.all_products:
            acr.limit_products.set([item_map[o.pk] for o in oldacr.limit_products.all()])
            acr.limit_variations.set(
                [variation_map[o.pk] for o in oldacr.limit_variations.all()]
            )


def perform_auto_checkin(sender, order, mode, payment_methods):
    positions = list(order.positions.all())
    payment_q = Q(all_payment_methods=True)
    for p in payment_methods:
        payment_q = payment_q | Q(limit_payment_methods__contains=p)

    rules = list(
        sender.autocheckinrule_set.filter(
            Q(all_sales_channels=True) | Q(limit_sales_channels=order.sales_channel_id),
            Q(all_products=True)
            | Q(limit_products__in=[op.item_id for op in positions])
            | Q(limit_variations__in=[op.variation_id for op in positions]),
            payment_q,
            mode=mode,
        )
        .distinct()
        .select_related("list")
        .prefetch_related("limit_products", "limit_variations")
    )

    if any(r.list is None for r in rules):
        all_lists = sender.checkin_lists.filter(
            Q(subevent__isnull=True)
            | Q(subevent__in=[op.subevent_id for op in positions])
        ).prefetch_related("limit_products")
    else:
        all_lists = []

    for r in rules:
        r_item_ids = {i.pk for i in r.limit_products.all()}
        r_variation_ids = {v.pk for v in r.limit_variations.all()}
        if r.list is not None:
            lists = [r.list]
        else:
            lists = all_lists

        for cl in lists:
            for op in positions:
                if not cl.all_products and op.item_id not in {
                    i.pk for i in cl.limit_products.all()
                }:
                    continue

                if not (r.all_products or op.item_id in r_item_ids or op.variation_id in r_variation_ids):
                    continue

                if cl.subevent_id and cl.subevent_id != op.subevent_id:
                    continue

                ci, created = Checkin.objects.get_or_create(
                    position=op,
                    list=cl,
                    auto_checked_in=True,
                    type=Checkin.TYPE_ENTRY,
                )
                if created:
                    checkin_created.send(sender, checkin=ci)


@receiver(order_placed, dispatch_uid="autocheckin_order_placed")
def order_placed_receiver(sender, order, **kwargs):
    mode = AutoCheckinRule.MODE_PLACED
    payment_methods = set()
    perform_auto_checkin(sender, order, mode, payment_methods)


@receiver(order_paid, dispatch_uid="autocheckin_order_paid")
def order_paid_receiver(sender, order, **kwargs):
    mode = AutoCheckinRule.MODE_PAID
    payment_methods = {
        p.provider
        for p in order.payments.filter(
            state__in=[
                OrderPayment.PAYMENT_STATE_CONFIRMED,
                OrderPayment.PAYMENT_STATE_REFUNDED,
            ]
        )
    }
    perform_auto_checkin(sender, order, mode, payment_methods)
