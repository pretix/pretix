from django.db.models import Count, Sum
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import ItemCategory, Order, OrderPosition


def tuplesum(tuples):
    return tuple(map(sum, zip(*list(tuples))))


def order_overview(event):
    items = event.items.all().select_related(
        'category',  # for re-grouping
    ).prefetch_related(
        'properties',  # for .get_all_available_variations()
    ).order_by('category__position', 'category_id', 'name')

    num_total = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in
        OrderPosition.objects.current.filter(order__event=event).values('item', 'variation').annotate(
            cnt=Count('id'), price=Sum('price'))
        }
    num_cancelled = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in (OrderPosition.objects.current
                  .filter(order__event=event, order__status=Order.STATUS_CANCELLED)
                  .values('item', 'variation')
                  .annotate(cnt=Count('id'), price=Sum('price')))
        }
    num_refunded = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in (OrderPosition.objects.current
                  .filter(order__event=event, order__status=Order.STATUS_REFUNDED)
                  .values('item', 'variation')
                  .annotate(cnt=Count('id'), price=Sum('price')))
        }
    num_pending = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in (OrderPosition.objects.current
                  .filter(order__event=event,
                          order__status__in=(Order.STATUS_PENDING, Order.STATUS_EXPIRED))
                  .values('item', 'variation')
                  .annotate(cnt=Count('id'), price=Sum('price')))
        }
    num_paid = {
        (p['item'], p['variation']): (p['cnt'], p['price'])
        for p in (OrderPosition.objects.current
                  .filter(order__event=event, order__status=Order.STATUS_PAID)
                  .values('item', 'variation')
                  .annotate(cnt=Count('id'), price=Sum('price')))
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

    total = {
        'num_total': tuplesum(c.num_total for c, i in items_by_category),
        'num_pending': tuplesum(c.num_pending for c, i in items_by_category),
        'num_cancelled': tuplesum(c.num_cancelled for c, i in items_by_category),
        'num_refunded': tuplesum(c.num_refunded for c, i in items_by_category),
        'num_paid': tuplesum(c.num_paid for c, i in items_by_category)
    }

    return items_by_category, total
