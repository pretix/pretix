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
from datetime import datetime
from typing import Optional

from django.conf import settings
from django.db.models import (
    Count, Exists, IntegerField, OuterRef, Prefetch, Q, Value,
)
from django.db.models.lookups import Exact

from pretix.base.models import (
    ItemVariation, Quota, SalesChannel, SeatCategoryMapping,
)
from pretix.base.models.items import (
    Item, ItemAddOn, ItemBundle, SubEventItem, SubEventItemVariation,
)
from pretix.base.services.quotas import QuotaAvailability
from pretix.base.timemachine import time_machine_now
from pretix.presale.signals import item_description


def item_group_by_category(items):
    return sorted(
        [
            # a group is a tuple of a category and a list of items
            (cat, [i for i in items if i.category == cat])
            for cat in set([i.category for i in items])
            # insert categories into a set for uniqueness
            # a set is unsorted, so sort again by category
        ],
        key=lambda group: (group[0].position, group[0].id) if (
            group[0] is not None and group[0].id is not None) else (0, 0)
    )


def prepare_item_list_for_shop(event, *, channel: SalesChannel, subevent=None, voucher=None, require_seat=0, base_qs=None,
                               allow_addons=False, allow_cross_sell=False,
                               quota_cache=None, filter_items=None, filter_categories=None, memberships=None,
                               ignore_hide_sold_out_for_item_ids=None):
    base_qs_set = base_qs is not None
    base_qs = base_qs if base_qs is not None else event.items

    requires_seat = Exists(
        SeatCategoryMapping.objects.filter(
            product_id=OuterRef('pk'),
            subevent=subevent
        )
    )
    if not event.settings.seating_choice:
        requires_seat = Value(0, output_field=IntegerField())

    variation_q = (
        Q(Q(available_from__isnull=True) | Q(available_from__lte=time_machine_now()) | Q(available_from_mode='info')) &
        Q(Q(available_until__isnull=True) | Q(available_until__gte=time_machine_now()) | Q(available_until_mode='info'))
    )
    if not voucher or not voucher.show_hidden_items:
        variation_q &= Q(hide_without_voucher=False)

    if memberships is not None:
        prefetch_membership_types = ['require_membership_types']
    else:
        prefetch_membership_types = []

    prefetch_var = Prefetch(
        'variations',
        to_attr='available_variations',
        queryset=ItemVariation.objects.using(settings.DATABASE_REPLICA).annotate(
            subevent_disabled=Exists(
                SubEventItemVariation.objects.filter(
                    Q(disabled=True)
                    | (Exact(OuterRef('available_from_mode'), 'hide') & Q(available_from__gt=time_machine_now()))
                    | (Exact(OuterRef('available_until_mode'), 'hide') & Q(available_until__lt=time_machine_now())),
                    variation_id=OuterRef('pk'),
                    subevent=subevent,
                )
            ),
        ).filter(
            variation_q,
            Q(all_sales_channels=True) | Q(limit_sales_channels=channel),
            Exists(Quota.variations.through.objects.filter(quota__subevent_id=subevent, itemvariation_id=OuterRef("pk"))),
            active=True,
            subevent_disabled=False
        ).prefetch_related(
            *prefetch_membership_types,
            Prefetch('quotas',
                     to_attr='_subevent_quotas',
                     queryset=event.quotas.using(settings.DATABASE_REPLICA).filter(
                         subevent=subevent).select_related("subevent"))
        ).distinct()
    )
    prefetch_quotas = Prefetch(
        'quotas',
        to_attr='_subevent_quotas',
        queryset=event.quotas.using(settings.DATABASE_REPLICA).filter(subevent=subevent).select_related("subevent")
    )
    prefetch_bundles = Prefetch(
        'bundles',
        queryset=ItemBundle.objects.using(settings.DATABASE_REPLICA).prefetch_related(
            Prefetch('bundled_item',
                     queryset=event.items.using(settings.DATABASE_REPLICA).select_related(
                         'tax_rule').prefetch_related(
                         Prefetch('quotas',
                                  to_attr='_subevent_quotas',
                                  queryset=event.quotas.using(settings.DATABASE_REPLICA).filter(
                                      subevent=subevent)),
                     )),
            Prefetch('bundled_variation',
                     queryset=ItemVariation.objects.using(
                         settings.DATABASE_REPLICA
                     ).select_related('item', 'item__tax_rule').filter(item__event=event).prefetch_related(
                         Prefetch('quotas',
                                  to_attr='_subevent_quotas',
                                  queryset=event.quotas.using(settings.DATABASE_REPLICA).filter(
                                      subevent=subevent)),
                     )),
        )
    )

    items = base_qs.using(settings.DATABASE_REPLICA).filter_available(
        channel=channel.identifier, voucher=voucher, allow_addons=allow_addons, allow_cross_sell=allow_cross_sell
    ).select_related(
        'category', 'tax_rule',  # for re-grouping
        'hidden_if_available',
    ).prefetch_related(
        *prefetch_membership_types,
        Prefetch(
            'hidden_if_item_available',
            queryset=event.items.annotate(
                has_variations=Count('variations'),
            ).prefetch_related(
                prefetch_var,
                prefetch_quotas,
                prefetch_bundles,
            )
        ),
        prefetch_quotas,
        prefetch_var,
        prefetch_bundles,
    ).annotate(
        has_variations=Count('variations'),
        subevent_disabled=Exists(
            SubEventItem.objects.filter(
                Q(disabled=True)
                | (Exact(OuterRef('available_from_mode'), 'hide') & Q(available_from__gt=time_machine_now()))
                | (Exact(OuterRef('available_until_mode'), 'hide') & Q(available_until__lt=time_machine_now())),
                item_id=OuterRef('pk'),
                subevent=subevent,
            )
        ),
        mandatory_priced_addons=Exists(
            ItemAddOn.objects.filter(
                base_item_id=OuterRef('pk'),
                min_count__gte=1,
                price_included=False
            )
        ),
        requires_seat=requires_seat,
    ).filter(
        Exists(Quota.items.through.objects.filter(quota__subevent_id=subevent, item_id=OuterRef("pk"))),
        subevent_disabled=False,
    ).order_by('category__position', 'category_id', 'position', 'name')
    if require_seat:
        items = items.filter(requires_seat__gt=0)
    elif require_seat is not None:
        items = items.filter(requires_seat=0)

    if filter_items:
        items = items.filter(pk__in=[a for a in filter_items if a.isdigit()])
    if filter_categories:
        items = items.filter(category_id__in=[a for a in filter_categories if a.isdigit()])

    display_add_to_cart = False
    quota_cache_key = f'item_quota_cache:{subevent.id if subevent else 0}:{channel.identifier}:{bool(require_seat)}'
    quota_cache = quota_cache or event.cache.get(quota_cache_key) or {}
    quota_cache_existed = bool(quota_cache)

    if subevent:
        item_price_override = subevent.item_price_overrides
        var_price_override = subevent.var_price_overrides
    else:
        item_price_override = {}
        var_price_override = {}

    restrict_vars = set()
    if voucher and voucher.quota_id:
        # If a voucher is set to a specific quota, we need to filter out on that level
        restrict_vars = set(voucher.quota.variations.all())

    quotas_to_compute = []
    for item in items:
        assert item.event_id == event.pk
        item.event = event  # save a database query if this is looked up
        if item.has_variations:
            for v in item.available_variations:
                for q in v._subevent_quotas:
                    if q.pk not in quota_cache:
                        quotas_to_compute.append(q)
        else:
            for q in item._subevent_quotas:
                if q.pk not in quota_cache:
                    quotas_to_compute.append(q)

    if quotas_to_compute:
        qa = QuotaAvailability()
        qa.queue(*quotas_to_compute)
        qa.compute()
        quota_cache.update({q.pk: r for q, r in qa.results.items()})

    for item in items:
        if voucher and voucher.item_id and voucher.variation_id:
            # Restrict variations if the voucher only allows one
            item.available_variations = [v for v in item.available_variations
                                         if v.pk == voucher.variation_id]

        if channel.type_instance.unlimited_items_per_order:
            max_per_order = sys.maxsize
        else:
            max_per_order = item.max_per_order or int(event.settings.max_items_per_order)
        if voucher:
            max_per_order = min(max_per_order, voucher.max_usages - voucher.redeemed)

        if item.hidden_if_available:
            q = item.hidden_if_available.availability(_cache=quota_cache)
            if q[0] == Quota.AVAILABILITY_OK:
                item._remove = True
                continue

        if item.hidden_if_item_available:
            if item.hidden_if_item_available.has_variations:
                item._dependency_available = any(
                    var.check_quotas(subevent=subevent, _cache=quota_cache, include_bundled=True)[0] == Quota.AVAILABILITY_OK
                    for var in item.hidden_if_item_available.available_variations
                )
            else:
                q = item.hidden_if_item_available.check_quotas(subevent=subevent, _cache=quota_cache, include_bundled=True)
                time_available = item.hidden_if_item_available.is_available()
                item._dependency_available = (q[0] == Quota.AVAILABILITY_OK) and time_available
            if item._dependency_available and item.hidden_if_item_available_mode == Item.UNAVAIL_MODE_HIDDEN:
                item._remove = True
                continue

        if item.require_membership and item.require_membership_hidden:
            if not memberships or not any([m.membership_type in item.require_membership_types.all() for m in memberships]):
                item._remove = True
                continue

        item.current_unavailability_reason = _get_item_unavailability_reason(item, has_voucher=voucher, subevent=subevent)

        item.description = str(item.description)
        for recv, resp in item_description.send(sender=event, item=item, variation=None, subevent=subevent):
            if resp:
                item.description += ("<br/>" if item.description else "") + resp

        if not item.has_variations:
            item._remove = False
            if not bool(item._subevent_quotas):
                item._remove = True
                continue

            if voucher and (voucher.allow_ignore_quota or voucher.block_quota):
                item.cached_availability = (
                    Quota.AVAILABILITY_OK, voucher.max_usages - voucher.redeemed
                )
            else:
                item.cached_availability = list(
                    item.check_quotas(subevent=subevent, _cache=quota_cache, include_bundled=True)
                )

            if not (
                    ignore_hide_sold_out_for_item_ids and item.pk in ignore_hide_sold_out_for_item_ids
            ) and event.settings.hide_sold_out and item.cached_availability[0] < Quota.AVAILABILITY_RESERVED:
                item._remove = True
                continue

            item.order_max = min(
                item.cached_availability[1]
                if item.cached_availability[1] is not None else sys.maxsize,
                max_per_order
            )

            original_price = item_price_override.get(item.pk, item.default_price)
            voucher_reduced = False
            if voucher:
                price = voucher.calculate_price(original_price)
                voucher_reduced = price < original_price
                include_bundled = not voucher.all_bundles_included
            else:
                price = original_price
                include_bundled = True

            item.display_price = item.tax(price, currency=event.currency, include_bundled=include_bundled)
            if item.free_price and item.free_price_suggestion is not None and not voucher_reduced:
                item.suggested_price = item.tax(max(price, item.free_price_suggestion), currency=event.currency, include_bundled=include_bundled)
            else:
                item.suggested_price = item.display_price

            if price != original_price:
                item.original_price = item.tax(original_price, currency=event.currency, include_bundled=True)
            else:
                item.original_price = (
                    item.tax(item.original_price, currency=event.currency, include_bundled=True,
                             base_price_is='net' if event.settings.display_net_prices else 'gross')  # backwards-compat
                    if item.original_price else None
                )
            if not display_add_to_cart:
                display_add_to_cart = not item.requires_seat and item.order_max > 0
        else:
            for var in item.available_variations:
                if var.require_membership and var.require_membership_hidden:
                    if not memberships or not any([m.membership_type in var.require_membership_types.all() for m in memberships]):
                        var._remove = True
                        continue

                var.description = str(var.description)
                for recv, resp in item_description.send(sender=event, item=item, variation=var, subevent=subevent):
                    if resp:
                        var.description += ("<br/>" if var.description else "") + resp

                if voucher and (voucher.allow_ignore_quota or voucher.block_quota):
                    var.cached_availability = (
                        Quota.AVAILABILITY_OK, voucher.max_usages - voucher.redeemed
                    )
                else:
                    var.cached_availability = list(
                        var.check_quotas(subevent=subevent, _cache=quota_cache, include_bundled=True)
                    )

                var.order_max = min(
                    var.cached_availability[1]
                    if var.cached_availability[1] is not None else sys.maxsize,
                    max_per_order
                )

                original_price = var_price_override.get(var.pk, var.price)
                voucher_reduced = False
                if voucher:
                    price = voucher.calculate_price(original_price)
                    voucher_reduced = price < original_price
                    include_bundled = not voucher.all_bundles_included
                else:
                    price = original_price
                    include_bundled = True

                var.display_price = var.tax(price, currency=event.currency, include_bundled=include_bundled)

                if item.free_price and var.free_price_suggestion is not None and not voucher_reduced:
                    var.suggested_price = item.tax(max(price, var.free_price_suggestion), currency=event.currency,
                                                   include_bundled=include_bundled)
                elif item.free_price and item.free_price_suggestion is not None and not voucher_reduced:
                    var.suggested_price = item.tax(max(price, item.free_price_suggestion), currency=event.currency,
                                                   include_bundled=include_bundled)
                else:
                    var.suggested_price = var.display_price

                if price != original_price:
                    var.original_price = var.tax(original_price, currency=event.currency, include_bundled=True)
                else:
                    var.original_price = (
                        var.tax(var.original_price or item.original_price, currency=event.currency,
                                include_bundled=True,
                                base_price_is='net' if event.settings.display_net_prices else 'gross')  # backwards-compat
                    ) if var.original_price or item.original_price else None

                var.current_unavailability_reason = _get_variant_unavailability_reason(var, has_voucher=voucher, subevent=subevent)

            item.original_price = (
                item.tax(item.original_price, currency=event.currency, include_bundled=True,
                         base_price_is='net' if event.settings.display_net_prices else 'gross')  # backwards-compat
                if item.original_price else None
            )

            item.available_variations = [
                v for v in item.available_variations if v._subevent_quotas and (
                    not voucher or not voucher.quota_id or v in restrict_vars
                ) and not getattr(v, '_remove', False)
            ]

            if not (ignore_hide_sold_out_for_item_ids and item.pk in ignore_hide_sold_out_for_item_ids) and event.settings.hide_sold_out:
                item.available_variations = [v for v in item.available_variations
                                             if v.cached_availability[0] >= Quota.AVAILABILITY_RESERVED]

            if voucher and voucher.variation_id:
                item.available_variations = [v for v in item.available_variations
                                             if v.pk == voucher.variation_id]

            if len(item.available_variations) > 0:
                item.min_price = min([v.display_price.net if event.settings.display_net_prices else
                                      v.display_price.gross for v in item.available_variations])
                item.max_price = max([v.display_price.net if event.settings.display_net_prices else
                                      v.display_price.gross for v in item.available_variations])
                item.best_variation_availability = max([v.cached_availability[0] for v in item.available_variations])

            item._remove = not bool(item.available_variations)
            if not item._remove and not display_add_to_cart:
                display_add_to_cart = not item.requires_seat and any(v.order_max > 0 for v in item.available_variations)

    if not quota_cache_existed and not voucher and not allow_addons and not base_qs_set and not filter_items and not filter_categories:
        event.cache.set(quota_cache_key, quota_cache, 5)
    items = [item for item in items
             if (len(item.available_variations) > 0 or not item.has_variations) and not item._remove]
    return items, display_add_to_cart


def _get_item_unavailability_reason(item, now_dt: Optional[datetime]=None, has_voucher=False, subevent=None) -> Optional[str]:
    now_dt = now_dt or time_machine_now()
    subevent_item = subevent and subevent.item_overrides.get(item.pk)
    if not item.active:
        return 'active'
    elif item.available_from and item.available_from > now_dt:
        return 'available_from'
    elif item.available_until and item.available_until < now_dt:
        return 'available_until'
    elif (item.require_voucher or item.hide_without_voucher) and not has_voucher:
        return 'require_voucher'
    elif subevent_item and subevent_item.available_from and subevent_item.available_from > now_dt:
        return 'available_from'
    elif subevent_item and subevent_item.available_until and subevent_item.available_until < now_dt:
        return 'available_until'
    elif item.hidden_if_item_available and item._dependency_available:
        return 'hidden_if_item_available'
    else:
        return None


def _get_variant_unavailability_reason(variant, now_dt: Optional[datetime]=None, has_voucher=False, subevent=None) -> Optional[str]:
    now_dt = now_dt or time_machine_now()
    subevent_var = subevent and subevent.var_overrides.get(variant.pk)
    if not variant.active:
        return 'active'
    elif variant.available_from and variant.available_from > now_dt:
        return 'available_from'
    elif variant.available_until and variant.available_until < now_dt:
        return 'available_until'
    elif subevent_var and subevent_var.available_from and subevent_var.available_from > now_dt:
        return 'available_from'
    elif subevent_var and subevent_var.available_until and subevent_var.available_until < now_dt:
        return 'available_until'
    else:
        return None
