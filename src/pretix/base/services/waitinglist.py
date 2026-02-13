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
import sys
from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import (
    Exists, F, OuterRef, Prefetch, Q, Sum, prefetch_related_objects,
)
from django.dispatch import receiver
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, EventMetaValue, SeatCategoryMapping, User, WaitingListEntry,
)
from pretix.base.models.waitinglist import WaitingListException
from pretix.base.services.locking import lock_objects
from pretix.base.services.tasks import EventTask
from pretix.base.signals import periodic_task
from pretix.celery_app import app


@app.task(base=EventTask)
def assign_automatically(event: Event, user_id: int=None, subevent_id: int=None):
    if user_id:
        user = User.objects.get(id=user_id)
    else:
        user = None

    quota_cache = {}
    gone = set()
    _seats_available_cache = {}
    seats_used = defaultdict(int)

    seated_product_set = set(
        SeatCategoryMapping.objects.filter(event=event).values_list('product_id', 'subevent_id')
    )

    def _seats_available(item, subevent):
        # See comment in WaitingListEntry.send_voucher() for rationale
        subevent_id = subevent.pk if subevent else None
        if (item.pk, subevent_id) not in _seats_available_cache:
            num_free_seats_for_product = (subevent or event).free_seats().filter(product_id=item.pk).count()
            num_valid_vouchers_for_product = event.vouchers.filter(
                Q(valid_until__isnull=True) | Q(valid_until__gte=now()),
                block_quota=True,
                item_id=item.pk,
                subevent_id=subevent_id,
                waitinglistentries__isnull=False
            ).aggregate(free=Sum(F('max_usages') - F('redeemed')))['free'] or 0
            _seats_available_cache[item.pk, subevent_id] = num_free_seats_for_product - num_valid_vouchers_for_product

        return _seats_available_cache[item.pk, subevent_id] - seats_used[item.pk, subevent_id]

    prefetch_related_objects(
        [event.organizer],
        'meta_properties'
    )
    prefetch_related_objects(
        [event],
        Prefetch(
            'meta_values',
            EventMetaValue.objects.select_related('property'),
            to_attr='meta_values_cached'
        )
    )

    qs = event.waitinglistentries.filter(
        voucher__isnull=True
    ).select_related('item', 'variation', 'subevent').prefetch_related(
        'item__quotas', 'variation__quotas'
    ).order_by('-priority', 'created', 'pk')

    if subevent_id and event.has_subevents:
        subevent = event.subevents.get(id=subevent_id)
        qs = qs.filter(subevent=subevent)

    sent = 0

    with transaction.atomic(durable=True):
        quotas_by_item = {}
        quotas = set()
        for wle in qs:
            if (wle.item_id, wle.variation_id, wle.subevent_id) not in quotas_by_item:
                quotas_by_item[wle.item_id, wle.variation_id, wle.subevent_id] = list(
                    wle.variation.quotas.filter(subevent=wle.subevent)
                    if wle.variation
                    else wle.item.quotas.filter(subevent=wle.subevent)
                )
            wle._quotas = quotas_by_item[wle.item_id, wle.variation_id, wle.subevent_id]
            quotas |= set(wle._quotas)

        lock_objects(quotas, shared_lock_objects=[event])
        for wle in qs:
            # add this event to wle.item as it is not yet cached and is needed in check_quotas
            wle.item.event = event
            if wle.variation:
                wle.variation.item = wle.item

            if (wle.item_id, wle.variation_id, wle.subevent_id) in gone:
                continue
            ev = (wle.subevent or event)
            if not ev.presale_is_running or (wle.subevent and not wle.subevent.active):
                continue
            if wle.subevent and not wle.subevent.presale_is_running:
                continue
            if event.settings.waiting_list_auto_disable and event.settings.waiting_list_auto_disable.datetime(wle.subevent or event) <= now():
                gone.add((wle.item_id, wle.variation_id, wle.subevent_id))
                continue
            if not wle.item.is_available():
                gone.add((wle.item_id, wle.variation_id, wle.subevent_id))
                continue

            if (wle.item_id, wle.subevent_id) in seated_product_set:
                if _seats_available(wle.item, wle.subevent) < 1:
                    gone.add((wle.item_id, wle.variation_id, wle.subevent_id))
                    continue

            availability = (
                wle.variation.check_quotas(count_waitinglist=False, _cache=quota_cache, subevent=wle.subevent)
                if wle.variation
                else wle.item.check_quotas(count_waitinglist=False, _cache=quota_cache, subevent=wle.subevent)
            )
            if availability[1] is None or availability[1] > 0:
                try:
                    wle.send_voucher(quota_cache, user=user)
                    sent += 1
                except WaitingListException:  # noqa
                    continue

                # Reduce affected quotas in cache
                for q in wle._quotas:
                    quota_cache[q.pk] = (
                        quota_cache[q.pk][0] if quota_cache[q.pk][0] > 1 else 0,
                        quota_cache[q.pk][1] - 1 if quota_cache[q.pk][1] is not None else sys.maxsize
                    )

                if (wle.item_id, wle.subevent_id) in seated_product_set:
                    seats_used[wle.item_id, wle.subevent_id] += 1
            else:
                gone.add((wle.item_id, wle.variation_id, wle.subevent_id))

    return sent


@receiver(signal=periodic_task)
@scopes_disabled()
def process_waitinglist(sender, **kwargs):
    qs = Event.objects.filter(
        Exists(
            WaitingListEntry.objects.filter(
                event_id=OuterRef('pk'),
                voucher__isnull=True,
            )
        ),
        live=True
    ).exclude(
        Q(date_to__isnull=True) | Q(date_to__lt=now() - timedelta(days=14)),
        Q(presale_end__isnull=True) | Q(presale_end__lt=now() - timedelta(days=14)),
        has_subevents=False,
        date_from__lt=now() - timedelta(days=14),
    ).prefetch_related('_settings_objects', 'organizer___settings_objects').select_related('organizer')
    for e in qs:
        if e.settings.waiting_list_auto and (e.presale_is_running or e.has_subevents):
            assign_automatically.apply_async(args=(e.pk,))
