from decimal import Decimal

from django.db.models import Count, Sum
from django.utils.translation import ugettext_lazy as _
from typing import Any, Dict, Iterable, List, Tuple

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


def order_overview(event: Event) -> Tuple[List[Tuple[ItemCategory, List[Item]]], Dict[str, Tuple[Decimal, Decimal]]]:
    items = event.items.all().select_related(
        'category',  # for re-grouping
    ).prefetch_related(
        'properties',  # for .get_all_available_variations()
    ).order_by('category__position', 'category_id', 'name')

    num_total = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in (OrderPosition.objects.current
                  .filter(order__event=event)
                  .values('item', 'variation')
                  .annotate(cnt=Count('id'), price=Sum('price')).order_by())
    }
    num_cancelled = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in (OrderPosition.objects.current
                  .filter(order__event=event, order__status=Order.STATUS_CANCELLED)
                  .values('item', 'variation')
                  .annotate(cnt=Count('id'), price=Sum('price')).order_by())
    }
    num_refunded = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in (OrderPosition.objects.current
                  .filter(order__event=event, order__status=Order.STATUS_REFUNDED)
                  .values('item', 'variation')
                  .annotate(cnt=Count('id'), price=Sum('price')).order_by())
    }
    num_pending = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in (OrderPosition.objects.current
                  .filter(order__event=event,
                          order__status__in=(Order.STATUS_PENDING, Order.STATUS_EXPIRED))
                  .values('item', 'variation')
                  .annotate(cnt=Count('id'), price=Sum('price')).order_by())
    }
    num_paid = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in (OrderPosition.objects.current
                  .filter(order__event=event, order__status=Order.STATUS_PAID)
                  .values('item', 'variation')
                  .annotate(cnt=Count('id'), price=Sum('price')).order_by())
    }

    for item in items:
        item.all_variations = sorted(item.get_all_variations(),
                                     key=lambda vd: vd.ordered_values())
        for var in item.all_variations:
            variid = var['variation'].identity if 'variation' in var else None
            var.num_total = num_total.get((item.identity, variid), (0, 0))
            var.num_pending = num_pending.get((item.identity, variid), (0, 0))
            var.num_cancelled = num_cancelled.get((item.identity, variid), (0, 0))
            var.num_refunded = num_refunded.get((item.identity, variid), (0, 0))
            var.num_paid = num_paid.get((item.identity, variid), (0, 0))
        item.has_variations = (len(item.all_variations) != 1
                               or not item.all_variations[0].empty())
        item.num_total = tuplesum(var.num_total for var in item.all_variations)
        item.num_pending = tuplesum(var.num_pending for var in item.all_variations)
        item.num_cancelled = tuplesum(var.num_cancelled for var in item.all_variations)
        item.num_refunded = tuplesum(var.num_refunded for var in item.all_variations)
        item.num_paid = tuplesum(var.num_paid for var in item.all_variations)

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
        key=lambda group: (group[0].position, group[0].identity) if group[0] is not None else (0, "")
    )

    for c in items_by_category:
        c[0].num_total = tuplesum(item.num_total for item in c[1])
        c[0].num_pending = tuplesum(item.num_pending for item in c[1])
        c[0].num_cancelled = tuplesum(item.num_cancelled for item in c[1])
        c[0].num_refunded = tuplesum(item.num_refunded for item in c[1])
        c[0].num_paid = tuplesum(item.num_paid for item in c[1])

    # Payment fees
    payment_cat_obj = DummyObject()
    payment_cat_obj.name = _('Payment method fees')
    payment_items = []
    num_total = {
        o['payment_provider']: (o['cnt'], o['payment_fee'])
        for o in (Order.objects.current
                  .filter(event=event)
                  .values('payment_provider')
                  .annotate(cnt=Count('id'), payment_fee=Sum('payment_fee')).order_by())
    }
    num_cancelled = {
        o['payment_provider']: (o['cnt'], o['payment_fee'])
        for o in (Order.objects.current
                  .filter(event=event, status=Order.STATUS_CANCELLED)
                  .values('payment_provider')
                  .annotate(cnt=Count('id'), payment_fee=Sum('payment_fee')).order_by())
    }
    num_refunded = {
        o['payment_provider']: (o['cnt'], o['payment_fee'])
        for o in (Order.objects.current
                  .filter(event=event, status=Order.STATUS_REFUNDED)
                  .values('payment_provider')
                  .annotate(cnt=Count('id'), payment_fee=Sum('payment_fee')).order_by())
    }
    num_pending = {
        o['payment_provider']: (o['cnt'], o['payment_fee'])
        for o in (Order.objects.current
                  .filter(event=event, status__in=(Order.STATUS_PENDING, Order.STATUS_EXPIRED))
                  .values('payment_provider')
                  .annotate(cnt=Count('id'), payment_fee=Sum('payment_fee')).order_by())
    }
    num_paid = {
        o['payment_provider']: (o['cnt'], o['payment_fee'])
        for o in (Order.objects.current
                  .filter(event=event, status=Order.STATUS_PAID)
                  .values('payment_provider')
                  .annotate(cnt=Count('id'), payment_fee=Sum('payment_fee')).order_by())
    }

    provider_names = {}
    responses = register_payment_providers.send(event)
    for receiver, response in responses:
        provider = response(event)
        provider_names[provider.identifier] = provider.verbose_name

    for pprov, total in num_total.items():
        ppobj = DummyObject()
        ppobj.name = provider_names.get(pprov, pprov)
        ppobj.has_variations = False
        ppobj.num_total = total
        ppobj.num_cancelled = num_cancelled.get(pprov, (0, 0))
        ppobj.num_refunded = num_refunded.get(pprov, (0, 0))
        ppobj.num_pending = num_pending.get(pprov, (0, 0))
        ppobj.num_paid = num_paid.get(pprov, (0, 0))
        payment_items.append(ppobj)

    payment_cat_obj.num_total = (Dontsum(''), sum(i.num_total[1] for i in payment_items))
    payment_cat_obj.num_cancelled = (Dontsum(''), sum(i.num_cancelled[1] for i in payment_items))
    payment_cat_obj.num_refunded = (Dontsum(''), sum(i.num_refunded[1] for i in payment_items))
    payment_cat_obj.num_pending = (Dontsum(''), sum(i.num_pending[1] for i in payment_items))
    payment_cat_obj.num_paid = (Dontsum(''), sum(i.num_paid[1] for i in payment_items))
    payment_cat = (payment_cat_obj, payment_items)

    items_by_category.append(payment_cat)

    total = {
        'num_total': tuplesum(c.num_total for c, i in items_by_category),
        'num_pending': tuplesum(c.num_pending for c, i in items_by_category),
        'num_cancelled': tuplesum(c.num_cancelled for c, i in items_by_category),
        'num_refunded': tuplesum(c.num_refunded for c, i in items_by_category),
        'num_paid': tuplesum(c.num_paid for c, i in items_by_category)
    }

    return items_by_category, total
