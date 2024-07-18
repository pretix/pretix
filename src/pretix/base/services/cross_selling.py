from collections import defaultdict
from decimal import Decimal
from itertools import groupby
from typing import List

from django.utils.functional import cached_property
from math import inf

from pretix.base.models import ItemCategory, CartPosition, SalesChannel
from pretix.presale.views.event import get_grouped_items


class DummyCategory:
    """
    Used to create fake category objects for displaying the same cross-selling category multiple times,
    once for each subevent
    """

    def __init__(self, category: ItemCategory, subevent=None):
        self.id = category.id
        self.name = category.name + (f" ({subevent})" if subevent else "")
        self.description = category.description


class CrossSellingService:
    def __init__(self, event, sales_channel: SalesChannel, cartpositions: List[CartPosition], customer):
        self.event = event
        self.sales_channel = sales_channel
        self.cartpositions = cartpositions
        self.customer = customer

    def get_data(self):
        if self.event.has_subevents:
            subevents = set(pos.subevent for pos in self.cartpositions)
            result = (
                (DummyCategory(category, subevent),
                 self._prepare_items(subevent, items_qs, discount_info),
                 f'subevent_{subevent.pk}_')
                for (category, items_qs, discount_info) in self._applicable_categories
                for subevent in subevents
            )
        else:
            result = (
                (category, self._prepare_items(None, items_qs, discount_info))
                for (category, items_qs, discount_info) in self._applicable_categories
            )
        return [(category, items) for (category, items) in result if len(items) > 0]

    @property
    def _applicable_categories(self):
        return [
            (c, products_qs, discount_info) for (c, products_qs, discount_info) in
            (
                (c, *self._get_visible_items_for_category(c))
                for c in self.event.categories.filter(cross_selling_mode__isnull=False)
            )
            if products_qs is not None
        ]

    def _get_visible_items_for_category(self, category: ItemCategory):
        """
        If this category should be visible in the cross-selling step for a given cart and sales_channel, this method
        returns a queryset of the items that should be displayed, as well as a dict giving additional information on them.

        :returns: (QuerySet<Item>, dict<item_pk: (max_count, discount_rule)>)
            max_count is `inf` if the item should not be limited
            discount_rule is None if the item will not be discounted
        """
        if category.cross_selling_mode is None:
            return None, {}
        if category.cross_selling_condition == 'always':
            return category.items.all(), {}
        if category.cross_selling_condition == 'products':
            match = set(match.pk for match in category.cross_selling_match_products.only('pk'))  # TODO prefetch this
            return (category.items.all(), {}) if any(pos.item.pk in match for pos in self.cartpositions) else (None, {})
        if category.cross_selling_condition == 'discounts':
            my_item_pks = category.items.values_list('pk', flat=True)
            potential_discount_items = {
                item.pk: (max_count, discount_rule)
                for item, max_count, discount_rule in self._potential_discounts_by_item_for_current_cart
                if max_count > 0 and item.pk in my_item_pks and item.is_available()
            }

            return category.items.filter(pk__in=potential_discount_items), potential_discount_items

    @cached_property
    def _potential_discounts_by_item_for_current_cart(self):
        potential_discounts_by_cartpos = defaultdict(list)

        from ..services.pricing import apply_discounts
        self._discounted_prices = apply_discounts(
            self.event,
            self.sales_channel,
            [
                (cp.item_id, cp.subevent_id, cp.line_price_gross, bool(cp.addon_to), cp.is_bundled,
                 cp.listed_price - cp.price_after_voucher)
                for cp in self.cartpositions
            ],
            collect_potential_discounts=potential_discounts_by_cartpos
        )

        # flatten potential_discounts_by_cartpos (a dict of lists of potential discounts) into a set of potential discounts
        # (which is technically stored as a dict, but we use it as an OrderedSet here)
        potential_discount_set = dict.fromkeys(
            info for lst in potential_discounts_by_cartpos.values() for info in lst)

        # sum up the max_counts and pass them on (also pass on the discount_rules so we can calculate actual discounted prices later):
        # group by benefit product
        # - max_count for product: sum up max_counts
        # - discount_rule for product: take first discount_rule

        def discount_info(item, infos_for_item):
            infos_for_item = list(infos_for_item)
            return (
                item,
                sum(max_count for (item, discount_rule, max_count, i) in infos_for_item),
                next(discount_rule for (item, discount_rule, max_count, i) in infos_for_item)
            )

        return [
            discount_info(item, infos_for_item) for item, infos_for_item in
            groupby(
                sorted(
                    (
                        (item, discount_rule, max_count, i)
                        for (discount_rule, max_count, i) in potential_discount_set.keys()
                        for item in discount_rule.benefit_limit_products.all()
                    ),
                    key=lambda tup: tup[0].pk
                ),
                lambda tup: tup[0])
        ]

    def _prepare_items(self, subevent, items_qs, discount_info):
        items, _btn = get_grouped_items(
            self.event,
            subevent=subevent,
            voucher=None,
            channel=self.sales_channel,
            base_qs=items_qs,
            allow_addons=True,
            allow_cross_sell=True,
            memberships=(
                self.customer.usable_memberships(
                    for_event=subevent or self.event,
                    testmode=self.event.testmode
                )
                if self.customer else None
            ),
        )
        new_items = list()
        for item in items:
            max_count = inf
            if item.pk in discount_info:
                (max_count, discount_rule) = discount_info[item.pk]

                # only benefit_only_apply_to_cheapest_n_matches discounted items have a max_count, all others get 'inf'
                if not max_count:
                    max_count = inf

                # calculate discounted price
                if discount_rule:
                    item.original_price = item.original_price or item.display_price
                    previous_price = item.display_price
                    new_price = (
                            previous_price * (
                                (Decimal('100.00') - discount_rule.benefit_discount_matching_percent) / Decimal('100.00'))
                    )
                    item.display_price = new_price

            # reduce order_max by number of items already in cart (prevent recommending a product the user can't add anyway)
            item.order_max = min(
                item.order_max - sum(1 for pos in self.cartpositions if pos.item_id == item.pk),
                max_count
            )
            if item.order_max > 0:
                new_items.append(item)

        return new_items

