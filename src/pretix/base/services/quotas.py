import sys
from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, F, Func, Max, Q, Sum
from django.dispatch import receiver
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    CartPosition, Event, LogEntry, Order, OrderPosition, Quota, Voucher,
    WaitingListEntry,
)
from pretix.celery_app import app

from ..signals import periodic_task, quota_availability


class QuotaAvailability:
    """
    This special object allows so tompute the availability of quotas and inspect their results.
    Initialize, add quotas with .queue(quota), compute with .compute() and access results.
    """

    def __init__(self, count_waitinglist=True, ignore_closed=False, full_results=False, early_out=True):
        self._queue = []
        self._count_waitinglist = count_waitinglist
        self._ignore_closed = ignore_closed
        self._full_results = full_results
        self._item_to_quota = defaultdict(list)
        self._var_to_quota = defaultdict(list)
        self._early_out = early_out
        self._quota_objects = {}
        self.results = {}
        self.count_paid_orders = defaultdict(int)
        self.count_pending_orders = defaultdict(int)
        self.count_vouchers = defaultdict(int)
        self.count_waitinglist = defaultdict(int)
        self.count_cart = defaultdict(int)

        self.sizes = {}

    def queue(self, *quota):
        self._queue += quota

    def compute(self, now_dt=None):
        now_dt = now_dt or now()
        quotas = list(self._queue)
        quotas_original = list(self._queue)
        self._queue.clear()
        if not quotas:
            return

        self._compute(quotas, now_dt)

        for q in quotas_original:
            for recv, resp in quota_availability.send(sender=q.event, quota=quotas_original, result=self.results[q],
                                                      count_waitinglist=self.count_waitinglist):
                self.results[q] = resp

        self._close(quotas)
        self._write_cache(quotas, now_dt)

    def _write_cache(self, quotas, now_dt):
        events = {q.event for q in quotas}
        update = []
        for e in events:
            e.cache.delete('item_quota_cache')
        for q in quotas:
            rewrite_cache = self._count_waitinglist and (
                not q.cache_is_hot(now_dt) or self.results[q][0] > q.cached_availability_state
                or q.cached_availability_paid_orders is None
            )
            if rewrite_cache:
                q.cached_availability_state = self.results[q][0]
                q.cached_availability_number = self.results[q][1]
                q.cached_availability_time = now_dt
                if q in self.count_paid_orders:
                    q.cached_availability_paid_orders = self.count_paid_orders[q]
                update.append(q)
        if update:
            Quota.objects.using('default').bulk_update(update, [
                'cached_availability_state', 'cached_availability_number', 'cached_availability_time',
                'cached_availability_paid_orders'
            ], batch_size=50)

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
            self._item_to_quota[m['item_id']].append(self._quota_objects[m['quota_id']])

        q_vars = Quota.variations.through.objects.filter(
            quota_id__in=[q.pk for q in quotas]
        ).values('quota_id', 'itemvariation_id')
        for m in q_vars:
            self._var_to_quota[m['itemvariation_id']].append(self._quota_objects[m['quota_id']])

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
        op_lookup = OrderPosition.objects.filter(
            order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING],
            order__event_id__in=events,
        ).filter(seq).filter(
            Q(
                Q(variation_id__isnull=True) &
                Q(item_id__in={i['item_id'] for i in q_items if self._quota_objects[i['quota_id']] in quotas})
            ) | Q(
                variation_id__in={i['itemvariation_id'] for i in q_vars if self._quota_objects[i['quota_id']] in quotas})
        ).order_by().values('order__status', 'item_id', 'subevent_id', 'variation_id').annotate(c=Count('*'))
        for line in sorted(op_lookup, key=lambda li: li['order__status'], reverse=True):  # p before n
            if line['variation_id']:
                qs = self._var_to_quota[line['variation_id']]
            else:
                qs = self._item_to_quota[line['item_id']]
            for q in qs:
                if q.subevent_id == line['subevent_id']:
                    size_left[q] -= line['c']
                    if line['order__status'] == Order.STATUS_PAID:
                        self.count_paid_orders[q] += line['c']
                        q.cached_availability_paid_orders = line['c']
                    elif line['order__status'] == Order.STATUS_PENDING:
                        self.count_pending_orders[q] += line['c']
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
                    Q(item_id__in={i['item_id'] for i in q_items if self._quota_objects[i['quota_id']] in quotas})
                ) | Q(
                    variation_id__in={i['itemvariation_id'] for i in q_vars if
                                      self._quota_objects[i['quota_id']] in quotas}
                ) | Q(
                    quota_id__in=[q.pk for q in quotas]
                )
            )
        ).order_by().values('subevent_id', 'item_id', 'quota_id', 'variation_id').annotate(
            free=Sum(Func(F('max_usages') - F('redeemed'), 0, function=func))
        )
        for line in v_lookup:
            if line['variation_id']:
                qs = self._var_to_quota[line['variation_id']]
            elif line['item_id']:
                qs = self._item_to_quota[line['item_id']]
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
                    Q(item_id__in={i['item_id'] for i in q_items if self._quota_objects[i['quota_id']] in quotas})
                ) | Q(
                    variation_id__in={i['itemvariation_id'] for i in q_vars if self._quota_objects[i['quota_id']] in quotas}
                )
            )
        ).order_by().values('item_id', 'subevent_id', 'variation_id').annotate(c=Count('*'))
        for line in cart_lookup:
            if line['variation_id']:
                qs = self._var_to_quota[line['variation_id']]
            else:
                qs = self._item_to_quota[line['item_id']]
            for q in qs:
                if q.subevent_id == line['subevent_id']:
                    size_left[q] -= line['c']
                    self.count_cart[q] += line['c']
                    if q not in self.results and size_left[q] <= 0:
                        self.results[q] = Quota.AVAILABILITY_RESERVED, 0

    def _compute_waitinglist(self, quotas, q_items, q_vars, size_left):
        events = {q.event_id for q in quotas}
        subevents = {q.subevent_id for q in quotas}
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
                    Q(item_id__in={i['item_id'] for i in q_items if self._quota_objects[i['quota_id']] in quotas})
                ) | Q(variation_id__in={i['itemvariation_id'] for i in q_vars if
                                        self._quota_objects[i['quota_id']] in quotas})
            )
        ).order_by().values('item_id', 'subevent_id', 'variation_id').annotate(c=Count('*'))
        for line in w_lookup:
            if line['variation_id']:
                qs = self._var_to_quota[line['variation_id']]
            else:
                qs = self._item_to_quota[line['item_id']]
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


@receiver(signal=periodic_task)
def build_all_quota_caches(sender, **kwargs):
    refresh_quota_caches.apply_async()


@app.task
@scopes_disabled()
def refresh_quota_caches():
    # Active events
    active = LogEntry.objects.using(settings.DATABASE_REPLICA).filter(
        datetime__gt=now() - timedelta(days=7)
    ).order_by().values('event').annotate(
        last_activity=Max('datetime')
    )
    for a in active:
        try:
            e = Event.objects.using(settings.DATABASE_REPLICA).get(pk=a['event'])
        except Event.DoesNotExist:
            continue
        quotas = e.quotas.filter(
            Q(cached_availability_time__isnull=True) |
            Q(cached_availability_time__lt=a['last_activity']) |
            Q(cached_availability_time__lt=now() - timedelta(hours=2))
        ).filter(
            Q(subevent__isnull=True) |
            Q(subevent__date_to__isnull=False, subevent__date_to__gte=now() - timedelta(days=14)) |
            Q(subevent__date_from__gte=now() - timedelta(days=14))
        )
        for q in quotas:
            q.availability()
