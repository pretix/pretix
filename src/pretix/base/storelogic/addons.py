import copy
from collections import defaultdict

from pretix.base.models.tax import TaxedPrice
from pretix.base.storelogic.products import get_items_for_product_list


def addons_is_completed(cart_positions):
    for cartpos in cart_positions.filter(addon_to__isnull=True).prefetch_related(
        'item__addons', 'item__addons__addon_category', 'addons', 'addons__item'
    ):
        a = cartpos.addons.all()
        for iao in cartpos.item.addons.all():
            found = len([1 for p in a if p.item.category_id == iao.addon_category_id and not p.is_bundled])
            if found < iao.min_count or found > iao.max_count:
                return False
    return True


def addons_is_applicable(cart_positions):
    return cart_positions.filter(item__addons__isnull=False).exists()


def get_addon_groups(event, sales_channel, customer, cart_positions):
    quota_cache = {}
    item_cache = {}
    groups = []
    for cartpos in sorted(cart_positions.filter(addon_to__isnull=True).prefetch_related(
        'item__addons', 'item__addons__addon_category', 'addons', 'addons__variation',
    ), key=lambda c: c.sort_key):
        groupentry = {
            'pos': cartpos,
            'item': cartpos.item,
            'variation': cartpos.variation,
            'categories': []
        }

        current_addon_products = defaultdict(list)
        for a in cartpos.addons.all():
            if not a.is_bundled:
                current_addon_products[a.item_id, a.variation_id].append(a)

        for iao in cartpos.item.addons.all():
            ckey = '{}-{}'.format(cartpos.subevent.pk if cartpos.subevent else 0, iao.addon_category.pk)

            if ckey not in item_cache:
                # Get all items to possibly show
                items, _btn = get_items_for_product_list(
                    event,
                    subevent=cartpos.subevent,
                    voucher=None,
                    channel=sales_channel,
                    base_qs=iao.addon_category.items,
                    allow_addons=True,
                    quota_cache=quota_cache,
                    memberships=(
                        customer.usable_memberships(
                            for_event=cartpos.subevent or event,
                            testmode=event.testmode
                        )
                        if customer else None
                    ),
                )
                item_cache[ckey] = items
            else:
                # We can use the cache to prevent a database fetch, but we need separate Python objects
                # or our things below like setting `i.initial` will do the wrong thing.
                items = [copy.copy(i) for i in item_cache[ckey]]
                for i in items:
                    i.available_variations = [copy.copy(v) for v in i.available_variations]

            for i in items:
                i.allow_waitinglist = False

                if i.has_variations:
                    for v in i.available_variations:
                        v.initial = len(current_addon_products[i.pk, v.pk])
                        if v.initial and i.free_price:
                            a = current_addon_products[i.pk, v.pk][0]
                            v.initial_price = TaxedPrice(
                                net=a.price - a.tax_value,
                                gross=a.price,
                                tax=a.tax_value,
                                name=a.item.tax_rule.name if a.item.tax_rule else "",
                                rate=a.tax_rate,
                                code=a.item.tax_rule.code if a.item.tax_rule else None,
                            )
                        else:
                            v.initial_price = v.suggested_price
                    i.expand = any(v.initial for v in i.available_variations)
                else:
                    i.initial = len(current_addon_products[i.pk, None])
                    if i.initial and i.free_price:
                        a = current_addon_products[i.pk, None][0]
                        i.initial_price = TaxedPrice(
                            net=a.price - a.tax_value,
                            gross=a.price,
                            tax=a.tax_value,
                            name=a.item.tax_rule.name if a.item.tax_rule else "",
                            rate=a.tax_rate,
                            code=a.item.tax_rule.code if a.item.tax_rule else None,
                        )
                    else:
                        i.initial_price = i.suggested_price

            if items:
                groupentry['categories'].append({
                    'category': iao.addon_category,
                    'price_included': iao.price_included or (cartpos.voucher_id and cartpos.voucher.all_addons_included),
                    'multi_allowed': iao.multi_allowed,
                    'min_count': iao.min_count,
                    'max_count': iao.max_count,
                    'iao': iao,
                    'items': items
                })
        if groupentry['categories']:
            groups.append(groupentry)
    return groups
