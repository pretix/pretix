from decimal import Decimal
from typing import Any, Dict, Iterable, List, Tuple

from django.db.models import Count, Sum
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event, Item, ItemCategory, Order, OrderPosition
from pretix.base.models.event import SubEvent
from pretix.base.models.orders import OrderFee
from pretix.base.signals import order_fee_type_name


class DummyObject:
    def __str__(self):
        return str(self.name)


class Dontsum:
    def __init__(self, value: Any):
        self.value = value

    def __str__(self) -> str:
        return str(self.value)


def tuplesum(tuples: Iterable[Tuple]) -> Tuple:
    """
    Takes a list of tuples of size n. In our case, those are e.g. tuples of size 2 containing
    a number of sales and a sum of their toal amount.

    Returned is again a tuple of size n. The first component of the returned tuple is the
    sum of the first components of all input tuples.

    Sample:

    >>> tuplesum([(1, 2), (3, 4), (5, 6)])
    (9, 12)
    """
    def mysum(it):
        # This method is identical to sum(list), except that it ignores entries of the type
        # Dontsum. We need this because we list the payment method fees seperately but we don't
        # want a order to contribute twice to the total count of orders (once for a product
        # and once for the payment method fee).
        sit = [i for i in it if not isinstance(i, Dontsum)]
        return sum(sit)

    # zip(*list(tuples)) basically transposes our input, e.g. [(1,2), (3,4), (5,6)]
    # becomes [(1, 3, 5), (2, 4, 6)]. We then call map on that, such that mysum((1, 3, 5))
    # and mysum((2, 4, 6)) will be called. The results will then be combined in a tuple again.
    return tuple(map(mysum, zip(*list(tuples))))


def dictsum(*dicts) -> dict:
    """
    Takes multiple dictionaries as arguments and builds a new dict. The input dict is expected
    to be a mapping of keys to tuples. The output dict will contain all keys that are
    present in any of the input dicts and will contain the tuplesum of all values associated
    with this key (see tuplesum function).

    Sample:

    >>> dictsum({'a': (1, 2), 'b': (3, 4)}, {'a': (5, 6), 'c': (7, 8)})
    {'a': (6, 8), 'b': (3, 4), 'c': (7, 8)}
    """
    res = {}
    keys = set()
    for d in dicts:
        keys |= set(d.keys())
    for k in keys:
        res[k] = tuplesum(d[k] for d in dicts if k in d)
    return res


def order_overview(event: Event, subevent: SubEvent=None) -> Tuple[List[Tuple[ItemCategory, List[Item]]],
                                                                   Dict[str, Tuple[Decimal, Decimal]]]:
    items = event.items.all().select_related(
        'category',  # for re-grouping
    ).prefetch_related(
        'variations'
    ).order_by('category__position', 'category_id', 'position', 'name')

    qs = OrderPosition.objects
    if subevent:
        qs = qs.filter(subevent=subevent)
    counters = qs.filter(
        order__event=event
    ).values(
        'item', 'variation', 'order__status'
    ).annotate(cnt=Count('id'), price=Sum('price'), tax_value=Sum('tax_value')).order_by()

    states = {
        'canceled': Order.STATUS_CANCELED,
        'refunded': Order.STATUS_REFUNDED,
        'paid': Order.STATUS_PAID,
        'pending': Order.STATUS_PENDING,
        'expired': Order.STATUS_EXPIRED,
    }
    num = {}
    for l, s in states.items():
        num[l] = {
            (p['item'], p['variation']): (p['cnt'], p['price'], p['price'] - p['tax_value'])
            for p in counters if p['order__status'] == s
        }

    num['total'] = dictsum(num['pending'], num['paid'])

    for item in items:
        item.all_variations = list(item.variations.all())
        item.has_variations = (len(item.all_variations) > 0)
        item.num = {}
        if item.has_variations:
            for var in item.all_variations:
                variid = var.id
                var.num = {}
                for l in states.keys():
                    var.num[l] = num[l].get((item.id, variid), (0, 0, 0))
                var.num['total'] = num['total'].get((item.id, variid), (0, 0, 0))
            for l in states.keys():
                item.num[l] = tuplesum(var.num[l] for var in item.all_variations)
            item.num['total'] = tuplesum(var.num['total'] for var in item.all_variations)
        else:
            for l in states.keys():
                item.num[l] = num[l].get((item.id, None), (0, 0, 0))
            item.num['total'] = num['total'].get((item.id, None), (0, 0, 0))

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
        c[0].num = {}
        for l in states.keys():
            c[0].num[l] = tuplesum(item.num[l] for item in c[1])
        c[0].num['total'] = tuplesum(item.num['total'] for item in c[1])

    # Payment fees
    payment_cat_obj = DummyObject()
    payment_cat_obj.name = _('Fees')
    payment_items = []

    if not subevent:
        counters = OrderFee.objects.filter(
            order__event=event
        ).values(
            'fee_type', 'internal_type', 'order__status'
        ).annotate(cnt=Count('id'), value=Sum('value'), tax_value=Sum('tax_value')).order_by()

        for l, s in states.items():
            num[l] = {
                (o['fee_type'], o['internal_type']): (o['cnt'], o['value'], o['value'] - o['tax_value'])
                for o in counters if o['order__status'] == s
            }
        num['total'] = dictsum(num['pending'], num['paid'])

        provider_names = {
            k: v.verbose_name
            for k, v in event.get_payment_providers().items()
        }
        names = dict(OrderFee.FEE_TYPES)

        for pprov, total in sorted(num['total'].items(), key=lambda i: i[0]):
            ppobj = DummyObject()
            if pprov[0] == OrderFee.FEE_TYPE_PAYMENT:
                ppobj.name = '{} - {}'.format(names[pprov[0]], provider_names.get(pprov[1], pprov[1]))
            else:
                name = pprov[1]
                for r, resp in order_fee_type_name.send(sender=event, fee_type=pprov[0], internal_type=pprov[1]):
                    if resp:
                        name = resp
                        break

                ppobj.name = '{} - {}'.format(names[pprov[0]], name)
            ppobj.provider = pprov[1]
            ppobj.has_variations = False
            ppobj.num = {}
            for l in states.keys():
                ppobj.num[l] = num[l].get(pprov, (0, 0, 0))
            ppobj.num['total'] = total
            payment_items.append(ppobj)

        payment_cat_obj.num = {}
        for l in states.keys():
            payment_cat_obj.num[l] = (
                Dontsum(''), sum(i.num[l][1] for i in payment_items), sum(i.num[l][2] for i in payment_items)
            )
        payment_cat_obj.num['total'] = (
            Dontsum(''), sum(i.num['total'][1] for i in payment_items), sum(i.num['total'][2] for i in payment_items)
        )
        payment_cat = (payment_cat_obj, payment_items)
        any_payment = any(payment_cat_obj.num[s][1] for s in states.keys())
        if any_payment:
            items_by_category.append(payment_cat)

    total = {
        'num': {'total': tuplesum(c.num['total'] for c, i in items_by_category)}
    }
    for l in states.keys():
        total['num'][l] = tuplesum(c.num[l] for c, i in items_by_category)

    return items_by_category, total
