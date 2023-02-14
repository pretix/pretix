#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
import time
from collections import Counter, defaultdict
from itertools import zip_longest

from django.conf import settings
from django.db import models
from django.db.models import (
    Case, Count, F, Func, Max, OuterRef, Q, Subquery, Sum, Value, When,
)
from django.utils.timezone import now
from django_redis import get_redis_connection

from pretix.base.models import (
    CartPosition, Checkin, Order, OrderPosition, Quota, Voucher,
    WaitingListEntry,
)

from ..signals import quota_availability


class QuotaAvailability:
    """
    This special object allows so compute the availability of multiple quotas, even across events, and inspect their
    results. The maximum number of SQL queries is constant and not dependent on the number of quotas.

    Usage example::

        qa = QuotaAvailability()
        qa.queue(quota1, quota2, …)
        qa.compute()
        print(qa.results)

    Properties you can access after computation.

    * results (dict mapping quotas to availability tuples)
    * count_paid_orders (dict mapping quotas to ints)
    * count_paid_orders (dict mapping quotas to ints)
    * count_pending_orders (dict mapping quotas to ints)
    * count_vouchers (dict mapping quotas to ints)
    * count_waitinglist (dict mapping quotas to ints)
    * count_cart (dict mapping quotas to ints)
    """

    def __init__(self, count_waitinglist=True, ignore_closed=False, full_results=False, early_out=True):
        """
        Initialize a new quota availability calculator

        :param count_waitinglist: If ``True`` (default), the waiting list is considered. If ``False``, it is ignored.

        :param ignore_closed: Quotas have a ``closed`` state that always makes the quota return as sold out. If you set
                              ``ignore_closed`` to ``True``, we will ignore this completely. Default is ``False``.

        :param full_results: Usually, the computation is as efficient as possible, i.e. if after counting the sold
                             orders we already see that the quota is sold out, we're not going to count the carts,
                             since it does not matter. This also means that you will not be able to get that number from
                             ``.count_cart``. If you want all parts to be calculated (i.e. because you want to show
                             statistics to the user), pass ``full_results`` and we'll skip that optimization.
                             items

        :param early_out: Usually, if a quota is ``closed`` or if its ``size`` is ``None`` (i.e. unlimited), we will
                          not need database access to determine the availability and return it right away. If you set
                          this to ``False``, however, we will *still* count the number of orders, which is required to
                          keep the database-level quota cache up to date so backend overviews render quickly. If you
                          do not care about keeping the cache up to date, you can set this to ``False`` for further
                          performance improvements.
        """
        self._queue = []
        self._count_waitinglist = count_waitinglist
        self._ignore_closed = ignore_closed
        self._full_results = full_results
        self._item_to_quotas = defaultdict(list)
        self._var_to_quotas = defaultdict(list)
        self._early_out = early_out
        self._quota_objects = {}
        self.results = {}
        self.count_paid_orders = defaultdict(int)
        self.count_pending_orders = defaultdict(int)
        self.count_exited_orders = defaultdict(int)
        self.count_vouchers = defaultdict(int)
        self.count_waitinglist = defaultdict(int)
        self.count_cart = defaultdict(int)

        self.sizes = {}

    def queue(self, *quota):
        self._queue += quota

    def compute(self, now_dt=None, allow_cache=False, allow_cache_stale=False):
        """
        Compute the queued quotas. If ``allow_cache`` is set, results may also be taken from a cache that might
        be a few minutes outdated. In this case, you may not rely on the results in the ``count_*`` properties.
        """
        now_dt = now_dt or now()
        quota_ids_set = {q.id for q in self._queue}
        if not quota_ids_set:
            return

        if allow_cache:
            if self._full_results:
                raise ValueError("You cannot combine full_results and allow_cache.")

            elif not self._count_waitinglist:
                raise ValueError("If you set allow_cache, you need to set count_waitinglist.")

            elif settings.HAS_REDIS:
                rc = get_redis_connection("redis")
                quotas_by_event = defaultdict(list)
                for q in [_q for _q in self._queue if _q.id in quota_ids_set]:
                    quotas_by_event[q.event_id].append(q)

                for eventid, evquotas in quotas_by_event.items():
                    d = rc.hmget(f'quotas:{eventid}:availabilitycache', [str(q.pk) for q in evquotas])
                    for redisval, q in zip(d, evquotas):
                        if redisval is not None:
                            data = [rv for rv in redisval.decode().split(',')]
                            # Except for some rare situations, we don't want to use cache entries older than 2 minutes
                            if time.time() - int(data[2]) < 120 or allow_cache_stale:
                                quota_ids_set.remove(q.id)
                                if data[1] == "None":
                                    self.results[q] = int(data[0]), None
                                else:
                                    self.results[q] = int(data[0]), int(data[1])

        if not quota_ids_set:
            return

        quotas = [_q for _q in self._queue if _q.id in quota_ids_set]
        quotas_original = list(quotas)
        self._queue.clear()

        self._compute(quotas, now_dt)

        for q in quotas_original:
            for recv, resp in quota_availability.send(sender=q.event, quota=q, result=self.results[q],
                                                      count_waitinglist=self.count_waitinglist):
                self.results[q] = resp

        self._close(quotas)
        self._write_cache(quotas, now_dt)

    def _write_cache(self, quotas, now_dt):
        if not settings.HAS_REDIS or not quotas:
            return

        rc = get_redis_connection("redis")
        # We write the computed availability to redis in a per-event hash as
        #
        #   quota_id -> (availability_state, availability_number, timestamp).
        #
        # We store this in a hash instead of inidividual values to avoid making two many redis requests
        # which would introduce latency.

        # The individual entries in the hash are "valid" for 120 seconds. This means in a typical peak scenario with
        # high load *to a specific calendar or event*, lots of parallel web requests will receive an "expired" result
        # around the same time, recompute quotas and write back to the cache. To avoid overloading redis with lots of
        # simultaneous write queries for the same page, we place a very naive and simple "lock" on the write process for
        # these quotas. We choose 10 seconds since that should be well above the duration of a write.

        lock_name = '_'.join([str(p) for p in sorted([q.pk for q in quotas])])
        if rc.exists(f'quotas:availabilitycachewrite:{lock_name}'):
            return
        rc.setex(f'quotas:availabilitycachewrite:{lock_name}', '1', 10)

        update = defaultdict(list)
        for q in quotas:
            update[q.event_id].append(q)

        for eventid, quotas in update.items():
            rc.hmset(f'quotas:{eventid}:availabilitycache', {
                str(q.id): ",".join(
                    [str(i) for i in self.results[q]] +
                    [str(int(time.time()))]
                ) for q in quotas
            })
            # To make sure old events do not fill up our redis instance, we set an expiry on the cache. However, we set it
            # on 7 days even though we mostly ignore values older than 2 monites. The reasoning is that we have some places
            # where we set allow_cache_stale and use the old entries anyways to save on performance.
            rc.expire(f'quotas:{eventid}:availabilitycache', 3600 * 24 * 7)

        # We used to also delete item_quota_cache:* from the event cache here, but as the cache
        # gets more complex, this does not seem worth it. The cache is only present for up to
        # 5 seconds to prevent high peaks, and a 5-second delay in availability is usually
        # tolerable

    def _close(self, quotas):
        for q in quotas:
            if self.results[q][0] <= Quota.AVAILABILITY_ORDERED and q.close_when_sold_out and not q.closed:
                q.closed = True
                q.save(update_fields=['closed'])
                q.log_action('pretix.event.quota.closed')

    def _compute(self, quotas, now_dt):
        # Quotas we want to look at now
        self.sizes.update({q: q.size for q in quotas})

        # Some helpful caches
        self._quota_objects.update({q.pk: q for q in quotas})

        # Compute result for closed or unlimited
        self._compute_early_outs(quotas)

        if self._early_out:
            if not self._full_results:
                quotas = [q for q in quotas if q not in self.results]
                if not quotas:
                    return

        size_left = Counter({q: (sys.maxsize if s is None else s) for q, s in self.sizes.items()})
        for q in quotas:
            self.count_paid_orders[q] = 0
            self.count_pending_orders[q] = 0
            self.count_cart[q] = 0
            self.count_vouchers[q] = 0
            self.count_waitinglist[q] = 0

        # Fetch which quotas belong to which items and variations
        q_items = Quota.items.through.objects.filter(
            quota_id__in=[q.pk for q in quotas]
        ).values('quota_id', 'item_id')
        for m in q_items:
            self._item_to_quotas[m['item_id']].append(self._quota_objects[m['quota_id']])

        q_vars = Quota.variations.through.objects.filter(
            quota_id__in=[q.pk for q in quotas]
        ).values('quota_id', 'itemvariation_id')
        for m in q_vars:
            self._var_to_quotas[m['itemvariation_id']].append(self._quota_objects[m['quota_id']])

        self._compute_orders(quotas, q_items, q_vars, size_left)

        if not self._full_results:
            quotas = [q for q in quotas if q not in self.results]
            if not quotas:
                return

        self._compute_vouchers(quotas, q_items, q_vars, size_left, now_dt)

        if not self._full_results:
            quotas = [q for q in quotas if q not in self.results]
            if not quotas:
                return

        self._compute_carts(quotas, q_items, q_vars, size_left, now_dt)

        if self._count_waitinglist:
            if not self._full_results:
                quotas = [q for q in quotas if q not in self.results]
                if not quotas:
                    return

            self._compute_waitinglist(quotas, q_items, q_vars, size_left)

        for q in quotas:
            if q not in self.results:
                if size_left[q] > 0:
                    self.results[q] = Quota.AVAILABILITY_OK, size_left[q]
                else:
                    raise ValueError("inconclusive quota")

    def _compute_orders(self, quotas, q_items, q_vars, size_left):
        events = {q.event_id for q in quotas}
        subevents = {q.subevent_id for q in quotas}
        seq = Q(subevent_id__in=subevents)
        if None in subevents:
            seq |= Q(subevent__isnull=True)
        quota_ids = {q.pk for q in quotas}
        op_lookup = OrderPosition.objects.filter(
            order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING],
            order__event_id__in=events,
        ).filter(seq).filter(
            Q(
                Q(variation_id__isnull=True) &
                Q(item_id__in={i['item_id'] for i in q_items if i['quota_id'] in quota_ids})
            ) | Q(
                variation_id__in={i['itemvariation_id'] for i in q_vars if i['quota_id'] in quota_ids})
        ).filter(
            ~Q(Q(ignore_from_quota_while_blocked=True) & Q(blocked__isnull=False))
        ).order_by()
        if any(q.release_after_exit for q in quotas):
            op_lookup = op_lookup.annotate(
                last_entry=Subquery(
                    Checkin.objects.filter(
                        position_id=OuterRef('pk'),
                        list__allow_entry_after_exit=False,
                        type=Checkin.TYPE_ENTRY,
                    ).order_by().values('position_id').annotate(
                        m=Max('datetime')
                    ).values('m')
                ),
                last_exit=Subquery(
                    Checkin.objects.filter(
                        position_id=OuterRef('pk'),
                        list__allow_entry_after_exit=False,
                        type=Checkin.TYPE_EXIT,
                    ).order_by().values('position_id').annotate(
                        m=Max('datetime')
                    ).values('m')
                ),
            ).annotate(
                is_exited=Case(
                    When(
                        Q(last_entry__isnull=False) & Q(last_exit__isnull=False) & Q(last_exit__gt=F('last_entry')),
                        then=Value(1, output_field=models.IntegerField()),
                    ),
                    default=Value(0, output_field=models.IntegerField()),
                    output_field=models.IntegerField(),
                ),
            )
        else:
            op_lookup = op_lookup.annotate(
                is_exited=Value(0, output_field=models.IntegerField())
            )
        op_lookup = op_lookup.values('order__status', 'item_id', 'subevent_id', 'variation_id', 'is_exited').annotate(c=Count('*'))
        for line in sorted(op_lookup, key=lambda li: (int(li['is_exited']), li['order__status']), reverse=True):  # p before n, exited before non-exited
            if line['variation_id']:
                qs = self._var_to_quotas[line['variation_id']]
            else:
                qs = self._item_to_quotas[line['item_id']]
            for q in qs:
                if q.subevent_id == line['subevent_id']:
                    if line['order__status'] == Order.STATUS_PAID:
                        self.count_paid_orders[q] += line['c']
                        q.cached_availability_paid_orders = self.count_paid_orders[q]
                    elif line['order__status'] == Order.STATUS_PENDING:
                        self.count_pending_orders[q] += line['c']
                    if q.release_after_exit and line['is_exited']:
                        self.count_exited_orders[q] += line['c']
                    else:
                        size_left[q] -= line['c']
                        if size_left[q] <= 0 and q not in self.results:
                            if line['order__status'] == Order.STATUS_PAID:
                                self.results[q] = Quota.AVAILABILITY_GONE, 0
                            else:
                                self.results[q] = Quota.AVAILABILITY_ORDERED, 0

    def _compute_vouchers(self, quotas, q_items, q_vars, size_left, now_dt):
        events = {q.event_id for q in quotas}
        if 'sqlite3' in settings.DATABASES['default']['ENGINE']:
            func = 'MAX'
        else:  # NOQA
            func = 'GREATEST'

        subevents = {q.subevent_id for q in quotas}
        quota_ids = {q.pk for q in quotas}
        seq = Q(subevent_id__in=subevents)
        if None in subevents:
            seq |= Q(subevent__isnull=True)
        v_lookup = Voucher.objects.filter(
            Q(event_id__in=events) &
            seq &
            Q(block_quota=True) &
            Q(Q(valid_until__isnull=True) | Q(valid_until__gte=now_dt)) &
            Q(
                Q(
                    Q(variation_id__isnull=True) &
                    Q(item_id__in={i['item_id'] for i in q_items if i['quota_id'] in quota_ids})
                ) | Q(
                    variation_id__in={i['itemvariation_id'] for i in q_vars if i['quota_id'] in quota_ids}
                ) | Q(
                    quota_id__in=[q.pk for q in quotas]
                )
            )
        ).order_by().values('subevent_id', 'item_id', 'quota_id', 'variation_id').annotate(
            free=Sum(Func(F('max_usages') - F('redeemed'), 0, function=func))
        )
        for line in v_lookup:
            if line['variation_id']:
                qs = self._var_to_quotas[line['variation_id']]
            elif line['item_id']:
                qs = self._item_to_quotas[line['item_id']]
            else:
                qs = [self._quota_objects[line['quota_id']]]
            for q in qs:
                if q.subevent_id == line['subevent_id']:
                    size_left[q] -= line['free']
                    self.count_vouchers[q] += line['free']
                    if q not in self.results and size_left[q] <= 0:
                        self.results[q] = Quota.AVAILABILITY_ORDERED, 0

    def _compute_carts(self, quotas, q_items, q_vars, size_left, now_dt):
        events = {q.event_id for q in quotas}
        subevents = {q.subevent_id for q in quotas}
        quota_ids = {q.pk for q in quotas}
        seq = Q(subevent_id__in=subevents)
        if None in subevents:
            seq |= Q(subevent__isnull=True)
        cart_lookup = CartPosition.objects.filter(
            Q(event_id__in=events) &
            seq &
            Q(expires__gte=now_dt) &
            Q(
                Q(voucher__isnull=True)
                | Q(voucher__block_quota=False)
                | Q(voucher__valid_until__lt=now_dt)
            ) &
            Q(
                Q(
                    Q(variation_id__isnull=True) &
                    Q(item_id__in={i['item_id'] for i in q_items if i['quota_id'] in quota_ids})
                ) | Q(
                    variation_id__in={i['itemvariation_id'] for i in q_vars if i['quota_id'] in quota_ids}
                )
            )
        ).order_by().values('item_id', 'subevent_id', 'variation_id').annotate(c=Count('*'))
        for line in cart_lookup:
            if line['variation_id']:
                qs = self._var_to_quotas[line['variation_id']]
            else:
                qs = self._item_to_quotas[line['item_id']]
            for q in qs:
                if q.subevent_id == line['subevent_id']:
                    size_left[q] -= line['c']
                    self.count_cart[q] += line['c']
                    if q not in self.results and size_left[q] <= 0:
                        self.results[q] = Quota.AVAILABILITY_RESERVED, 0

    def _compute_waitinglist(self, quotas, q_items, q_vars, size_left):
        events = {q.event_id for q in quotas}
        subevents = {q.subevent_id for q in quotas}
        quota_ids = {q.pk for q in quotas}
        seq = Q(subevent_id__in=subevents)
        if None in subevents:
            seq |= Q(subevent__isnull=True)
        w_lookup = WaitingListEntry.objects.filter(
            Q(event_id__in=events) &
            Q(voucher__isnull=True) &
            seq &
            Q(
                Q(
                    Q(variation_id__isnull=True) &
                    Q(item_id__in={i['item_id'] for i in q_items if i['quota_id'] in quota_ids})
                ) | Q(variation_id__in={i['itemvariation_id'] for i in q_vars if i['quota_id'] in quota_ids})
            )
        ).order_by().values('item_id', 'subevent_id', 'variation_id').annotate(c=Count('*'))
        for line in w_lookup:
            if line['variation_id']:
                qs = self._var_to_quotas[line['variation_id']]
            else:
                qs = self._item_to_quotas[line['item_id']]
            for q in qs:
                if q.subevent_id == line['subevent_id']:
                    size_left[q] -= line['c']
                    self.count_waitinglist[q] += line['c']
                    if q not in self.results and size_left[q] <= 0:
                        self.results[q] = Quota.AVAILABILITY_ORDERED, 0

    def _compute_early_outs(self, quotas):
        for q in quotas:
            if q.closed and not self._ignore_closed:
                self.results[q] = Quota.AVAILABILITY_ORDERED, 0
            elif q.size is None:
                self.results[q] = Quota.AVAILABILITY_OK, None
            elif q.size == 0:
                self.results[q] = Quota.AVAILABILITY_GONE, 0


def grouper(iterable, n, fillvalue=None):
    """Collect data into fixed-length chunks or blocks"""
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return zip_longest(fillvalue=fillvalue, *args)
