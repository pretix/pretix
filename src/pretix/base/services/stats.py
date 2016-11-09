from decimal import Decimal
from typing import Any, Dict, Iterable, List, Tuple

from django.db.models import Count, Sum
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event, Item, ItemCategory, Order, OrderPosition
from pretix.base.signals import register_payment_providers


class DummyObject:
    pass


class Dontsum:
    def __init__(self, value: Any):
        self.value = value

    def __str__(self) -> str:
        return str(self.value)


def tuplesum(tuples: Iterable[Tuple]) -> Tuple:
    def mysum(it):
        sit = [i for i in it if not isinstance(i, Dontsum)]
        return sum(sit)

    return tuple(map(mysum, zip(*list(tuples))))


def dictsum(*dicts) -> dict:
    res = {}
    keys = set()
    for d in dicts:
        keys |= set(d.keys())
    for k in keys:
        res[k] = (sum(d[k][0] for d in dicts if k in d), sum(d[k][1] for d in dicts if k in d))
    return res


def order_overview(event: Event) -> Tuple[List[Tuple[ItemCategory, List[Item]]], Dict[str, Tuple[Decimal, Decimal]]]:
    items = event.items.all().select_related(
        'category',  # for re-grouping
    ).prefetch_related(
        'variations'
    ).order_by('category__position', 'category_id', 'name')

    counters = OrderPosition.objects.filter(
        order__event=event
    ).values(
        'item', 'variation', 'order__status'
    ).annotate(cnt=Count('id'), price=Sum('price')).order_by()

    num_canceled = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in counters if p['order__status'] == Order.STATUS_CANCELED
    }
    num_refunded = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in counters if p['order__status'] == Order.STATUS_REFUNDED
    }
    num_paid = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in counters if p['order__status'] == Order.STATUS_PAID
    }
    num_s_pending = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in counters if p['order__status'] == Order.STATUS_PENDING
    }
    num_expired = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in counters if p['order__status'] == Order.STATUS_EXPIRED
    }
    num_pending = dictsum(num_s_pending, num_expired)
    num_total = dictsum(num_pending, num_paid)

    for item in items:
        item.all_variations = list(item.variations.all())
        item.has_variations = (len(item.all_variations) > 0)
        if item.has_variations:
            for var in item.all_variations:
                variid = var.id
                var.num_total = num_total.get((item.id, variid), (0, 0))
                var.num_pending = num_pending.get((item.id, variid), (0, 0))
                var.num_canceled = num_canceled.get((item.id, variid), (0, 0))
                var.num_refunded = num_refunded.get((item.id, variid), (0, 0))
                var.num_paid = num_paid.get((item.id, variid), (0, 0))
            item.num_total = tuplesum(var.num_total for var in item.all_variations)
            item.num_pending = tuplesum(var.num_pending for var in item.all_variations)
            item.num_canceled = tuplesum(var.num_canceled for var in item.all_variations)
            item.num_refunded = tuplesum(var.num_refunded for var in item.all_variations)
            item.num_paid = tuplesum(var.num_paid for var in item.all_variations)
        else:
            item.num_total = num_total.get((item.id, None), (0, 0))
            item.num_pending = num_pending.get((item.id, None), (0, 0))
            item.num_canceled = num_canceled.get((item.id, None), (0, 0))
            item.num_refunded = num_refunded.get((item.id, None), (0, 0))
            item.num_paid = num_paid.get((item.id, None), (0, 0))

    nonecat = ItemCategory(name=_('Uncategorized'))
    # Regroup those by category
    items_by_category = sorted(
        [
            # a group is a tuple of a category and a list of items
            (cat if cat is not None else nonecat, [i for i in items if i.category == cat])
            for cat in set([i.category for i in items])
            # insert categories into a set for uniqueness
            # a set is unsorted, so sort again by category
        ],
        key=lambda group: (group[0].position, group[0].id) if (
            group[0] is not None and group[0].id is not None) else (0, 0)
    )

    for c in items_by_category:
        c[0].num_total = tuplesum(item.num_total for item in c[1])
        c[0].num_pending = tuplesum(item.num_pending for item in c[1])
        c[0].num_canceled = tuplesum(item.num_canceled for item in c[1])
        c[0].num_refunded = tuplesum(item.num_refunded for item in c[1])
        c[0].num_paid = tuplesum(item.num_paid for item in c[1])

    # Payment fees
    payment_cat_obj = DummyObject()
    payment_cat_obj.name = _('Payment method fees')
    payment_items = []

    counters = event.orders.values('payment_provider', 'status').annotate(
        cnt=Count('id'), payment_fee=Sum('payment_fee')
    ).order_by()

    num_canceled = {
        o['payment_provider']: (o['cnt'], o['payment_fee'])
        for o in counters if o['status'] == Order.STATUS_CANCELED
    }
    num_refunded = {
        o['payment_provider']: (o['cnt'], o['payment_fee'])
        for o in counters if o['status'] == Order.STATUS_REFUNDED
    }
    num_s_pending = {
        o['payment_provider']: (o['cnt'], o['payment_fee'])
        for o in counters if o['status'] == Order.STATUS_PENDING
    }
    num_expired = {
        o['payment_provider']: (o['cnt'], o['payment_fee'])
        for o in counters if o['status'] == Order.STATUS_EXPIRED
    }
    num_paid = {
        o['payment_provider']: (o['cnt'], o['payment_fee'])
        for o in counters if o['status'] == Order.STATUS_PAID
    }
    num_pending = dictsum(num_s_pending, num_expired)
    num_total = dictsum(num_pending, num_paid)

    provider_names = {}
    responses = register_payment_providers.send(event)
    for receiver, response in responses:
        provider = response(event)
        provider_names[provider.identifier] = provider.verbose_name

    for pprov, total in num_total.items():
        ppobj = DummyObject()
        ppobj.name = provider_names.get(pprov, pprov)
        ppobj.provider = pprov
        ppobj.has_variations = False
        ppobj.num_total = total
        ppobj.num_canceled = num_canceled.get(pprov, (0, 0))
        ppobj.num_refunded = num_refunded.get(pprov, (0, 0))
        ppobj.num_pending = num_pending.get(pprov, (0, 0))
        ppobj.num_paid = num_paid.get(pprov, (0, 0))
        payment_items.append(ppobj)

    payment_cat_obj.num_total = (Dontsum(''), sum(i.num_total[1] for i in payment_items))
    payment_cat_obj.num_canceled = (Dontsum(''), sum(i.num_canceled[1] for i in payment_items))
    payment_cat_obj.num_refunded = (Dontsum(''), sum(i.num_refunded[1] for i in payment_items))
    payment_cat_obj.num_pending = (Dontsum(''), sum(i.num_pending[1] for i in payment_items))
    payment_cat_obj.num_paid = (Dontsum(''), sum(i.num_paid[1] for i in payment_items))
    payment_cat = (payment_cat_obj, payment_items)

    items_by_category.append(payment_cat)

    total = {
        'num_total': tuplesum(c.num_total for c, i in items_by_category),
        'num_pending': tuplesum(c.num_pending for c, i in items_by_category),
        'num_canceled': tuplesum(c.num_canceled for c, i in items_by_category),
        'num_refunded': tuplesum(c.num_refunded for c, i in items_by_category),
        'num_paid': tuplesum(c.num_paid for c, i in items_by_category)
    }

    return items_by_category, total
