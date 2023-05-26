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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Vishal Sodani, jasonwaiting@live.hk
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import calendar
import hashlib
import sys
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from urllib.parse import urlencode

import isoweek
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import (
    Count, Exists, IntegerField, OuterRef, Prefetch, Q, Value,
)
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.formats import get_format
from django.utils.functional import SimpleLazyObject
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from pretix.base.channels import get_all_sales_channels
from pretix.base.models import (
    ItemVariation, Quota, SeatCategoryMapping, Voucher,
)
from pretix.base.models.event import Event, SubEvent
from pretix.base.models.items import (
    ItemAddOn, ItemBundle, SubEventItem, SubEventItemVariation,
)
from pretix.base.services.quotas import QuotaAvailability
from pretix.helpers.compat import date_fromisocalendar
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.ical import get_public_ical
from pretix.presale.signals import item_description
from pretix.presale.views.organizer import (
    EventListMixin, add_subevents_for_days, days_for_template,
    filter_qs_by_attr, has_before_after, weeks_for_template,
)

from ...helpers.formats.en.formats import SHORT_MONTH_DAY_FORMAT, WEEK_FORMAT
from . import (
    CartMixin, EventViewMixin, allow_frame_if_namespaced, get_cart,
    iframe_entry_view_wrapper,
)

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore


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


def get_grouped_items(event, subevent=None, voucher=None, channel='web', require_seat=0, base_qs=None, allow_addons=False,
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
        Q(Q(available_from__isnull=True) | Q(available_from__lte=now())) &
        Q(Q(available_until__isnull=True) | Q(available_until__gte=now()))
    )
    if not voucher or not voucher.show_hidden_items:
        variation_q &= Q(hide_without_voucher=False)

    if memberships is not None:
        prefetch_membership_types = ['require_membership_types']
    else:
        prefetch_membership_types = []

    items = base_qs.using(settings.DATABASE_REPLICA).filter_available(channel=channel, voucher=voucher, allow_addons=allow_addons).select_related(
        'category', 'tax_rule',  # for re-grouping
        'hidden_if_available',
    ).prefetch_related(
        *prefetch_membership_types,
        Prefetch('quotas',
                 to_attr='_subevent_quotas',
                 queryset=event.quotas.using(settings.DATABASE_REPLICA).filter(subevent=subevent)),
        Prefetch('bundles',
                 queryset=ItemBundle.objects.using(settings.DATABASE_REPLICA).prefetch_related(
                     Prefetch('bundled_item',
                              queryset=event.items.using(settings.DATABASE_REPLICA).select_related('tax_rule').prefetch_related(
                                  Prefetch('quotas',
                                           to_attr='_subevent_quotas',
                                           queryset=event.quotas.using(settings.DATABASE_REPLICA).filter(subevent=subevent)),
                              )),
                     Prefetch('bundled_variation',
                              queryset=ItemVariation.objects.using(
                                  settings.DATABASE_REPLICA
                              ).select_related('item', 'item__tax_rule').filter(item__event=event).prefetch_related(
                                  Prefetch('quotas',
                                           to_attr='_subevent_quotas',
                                           queryset=event.quotas.using(settings.DATABASE_REPLICA).filter(subevent=subevent)),
                              )),
                 )),
        Prefetch('variations', to_attr='available_variations',
                 queryset=ItemVariation.objects.using(settings.DATABASE_REPLICA).annotate(
                     subevent_disabled=Exists(
                         SubEventItemVariation.objects.filter(
                             Q(disabled=True) | Q(available_from__gt=now()) | Q(available_until__lt=now()),
                             variation_id=OuterRef('pk'),
                             subevent=subevent,
                         )
                     ),
                 ).filter(
                     variation_q,
                     active=True,
                     sales_channels__contains=channel,
                     quotas__isnull=False,
                     subevent_disabled=False
                 ).prefetch_related(
                     *prefetch_membership_types,
                     Prefetch('quotas',
                              to_attr='_subevent_quotas',
                              queryset=event.quotas.using(settings.DATABASE_REPLICA).filter(subevent=subevent))
                 ).distinct()),
    ).annotate(
        quotac=Count('quotas'),
        has_variations=Count('variations'),
        subevent_disabled=Exists(
            SubEventItem.objects.filter(
                Q(disabled=True) | Q(available_from__gt=now()) | Q(available_until__lt=now()),
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
        quotac__gt=0, subevent_disabled=False,
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
    quota_cache_key = f'item_quota_cache:{subevent.id if subevent else 0}:{channel}:{bool(require_seat)}'
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

        if get_all_sales_channels()[channel].unlimited_items_per_order:
            max_per_order = sys.maxsize
        else:
            max_per_order = item.max_per_order or int(event.settings.max_items_per_order)

        if item.hidden_if_available:
            q = item.hidden_if_available.availability(_cache=quota_cache)
            if q[0] == Quota.AVAILABILITY_OK:
                item._remove = True
                continue

        if item.require_membership and item.require_membership_hidden:
            if not memberships or not any([m.membership_type in item.require_membership_types.all() for m in memberships]):
                item._remove = True
                continue

        item.description = str(item.description)
        for recv, resp in item_description.send(sender=event, item=item, variation=None):
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
            if voucher:
                price = voucher.calculate_price(original_price)
            else:
                price = original_price

            item.display_price = item.tax(price, currency=event.currency, include_bundled=True)

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
                for recv, resp in item_description.send(sender=event, item=item, variation=var):
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
                if voucher:
                    price = voucher.calculate_price(original_price)
                else:
                    price = original_price

                var.display_price = var.tax(price, currency=event.currency, include_bundled=True)

                if price != original_price:
                    var.original_price = var.tax(original_price, currency=event.currency, include_bundled=True)
                else:
                    var.original_price = (
                        var.tax(var.original_price or item.original_price, currency=event.currency,
                                include_bundled=True,
                                base_price_is='net' if event.settings.display_net_prices else 'gross')  # backwards-compat
                    ) if var.original_price or item.original_price else None

                if not display_add_to_cart:
                    display_add_to_cart = not item.requires_seat and var.order_max > 0

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

    if not quota_cache_existed and not voucher and not allow_addons and not base_qs_set and not filter_items and not filter_categories:
        event.cache.set(quota_cache_key, quota_cache, 5)
    items = [item for item in items
             if (len(item.available_variations) > 0 or not item.has_variations) and not item._remove]
    return items, display_add_to_cart


@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class EventIndex(EventViewMixin, EventListMixin, CartMixin, TemplateView):
    template_name = "pretixpresale/event/index.html"

    def get(self, request, *args, **kwargs):
        # redirect old month-year-URLs to new date-URLs
        keys = ("month", "year")
        if all(k in request.GET for k in keys):
            get_params = {k: v for k, v in request.GET.items() if k not in keys}
            get_params["date"] = "%s-%s" % (request.GET.get("year"), request.GET.get("month"))
            return redirect(self.request.path + "?" + urlencode(get_params))

        # redirect old week-year-URLs to new date-URLs
        keys = ("week", "year")
        if all(k in request.GET for k in keys):
            get_params = {k: v for k, v in request.GET.items() if k not in keys}
            get_params["date"] = "%s-W%s" % (request.GET.get("year"), request.GET.get("week"))
            return redirect(self.request.path + "?" + urlencode(get_params))

        from pretix.presale.views.cart import get_or_create_cart_id

        self.subevent = None
        if request.GET.get('src', '') == 'widget' and 'take_cart_id' in request.GET:
            # User has clicked "Open in a new tab" link in widget
            get_or_create_cart_id(request)
            return redirect(eventreverse(request.event, 'presale:event.index', kwargs=kwargs))
        elif request.GET.get('iframe', '') == '1' and 'take_cart_id' in request.GET:
            # Widget just opened, a cart already exists. Let's to a stupid redirect to check if cookies are disabled
            get_or_create_cart_id(request)
            return redirect(eventreverse(request.event, 'presale:event.index', kwargs=kwargs) + '?' + urllib.parse.urlencode({
                'require_cookie': 'true',
                'cart_id': request.GET.get('take_cart_id'),
                **({"locale": request.GET.get('locale')} if request.GET.get('locale') else {}),
            }))
        elif request.GET.get('iframe', '') == '1' and len(self.request.GET.get('widget_data', '{}')) > 3:
            # We've been passed data from a widget, we need to create a cart session to store it.
            get_or_create_cart_id(request)
        elif 'require_cookie' in request.GET and settings.SESSION_COOKIE_NAME not in request.COOKIES:
            # Cookies are in fact not supported
            r = render(request, 'pretixpresale/event/cookies.html', {
                'url': eventreverse(
                    request.event, "presale:event.index", kwargs={'cart_namespace': kwargs.get('cart_namespace') or ''}
                ) + "?" + urllib.parse.urlencode({
                    "src": "widget",
                    **({"locale": request.GET.get('locale')} if request.GET.get('locale') else {}),
                    **({"take_cart_id": request.GET.get('cart_id')} if request.GET.get('cart_id') else {}),
                })
            })
            r._csp_ignore = True
            return r

        if request.sales_channel.identifier not in request.event.sales_channels:
            raise Http404(_('Tickets for this event cannot be purchased on this sales channel.'))

        if request.event.has_subevents:
            if 'subevent' in kwargs:
                self.subevent = request.event.subevents.using(settings.DATABASE_REPLICA).filter(pk=kwargs['subevent'], active=True).first()
                if not self.subevent:
                    raise Http404()
                return super().get(request, *args, **kwargs)
            else:
                return super().get(request, *args, **kwargs)
        else:
            if 'subevent' in kwargs:
                return redirect(self.get_index_url())
            else:
                return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['ev'] = self.subevent or self.request.event
        context['subevent'] = self.subevent

        # Show voucher option if an event is selected and vouchers exist
        vouchers_exist = self.request.event.cache.get('vouchers_exist')
        if vouchers_exist is None:
            vouchers_exist = self.request.event.vouchers.exists()
            self.request.event.cache.set('vouchers_exist', vouchers_exist)
        context['show_vouchers'] = context['vouchers_exist'] = vouchers_exist and (
            (self.request.event.has_subevents and not self.subevent) or
            context['ev'].presale_is_running
        )

        context['allow_waitinglist'] = self.request.event.settings.waiting_list_enabled and context['ev'].presale_is_running

        if not self.request.event.has_subevents or self.subevent:
            # Fetch all items
            items, display_add_to_cart = get_grouped_items(
                self.request.event, self.subevent,
                filter_items=self.request.GET.getlist('item'),
                filter_categories=self.request.GET.getlist('category'),
                require_seat=None,
                channel=self.request.sales_channel.identifier,
                memberships=(
                    self.request.customer.usable_memberships(
                        for_event=self.subevent or self.request.event,
                        testmode=self.request.event.testmode
                    ) if getattr(self.request, 'customer', None) else None
                ),
            )

            context['waitinglist_seated'] = False
            if context['allow_waitinglist']:
                for i in items:
                    if not i.allow_waitinglist or not i.requires_seat:
                        continue

                    if i.has_variations:
                        for v in i.available_variations:
                            if v.cached_availability[0] != Quota.AVAILABILITY_OK:
                                context['waitinglist_seated'] = True
                                break
                    else:
                        if i.cached_availability[0] != Quota.AVAILABILITY_OK:
                            context['waitinglist_seated'] = True
                            break

            items = [i for i in items if not i.requires_seat]
            context['itemnum'] = len(items)
            context['allfree'] = all(
                item.display_price.gross == Decimal('0.00') for item in items if not item.has_variations
            ) and all(
                all(
                    var.display_price.gross == Decimal('0.00')
                    for var in item.available_variations
                )
                for item in items if item.has_variations
            )

            # Regroup those by category
            context['items_by_category'] = item_group_by_category(items)
            context['display_add_to_cart'] = display_add_to_cart

        context['cart'] = self.get_cart()
        context['has_addon_choices'] = any(cp.has_addon_choices for cp in get_cart(self.request))

        if self.subevent:
            context['frontpage_text'] = str(self.subevent.frontpage_text)
        else:
            context['frontpage_text'] = str(self.request.event.settings.frontpage_text)

        if self.request.event.has_subevents:
            context['subevent_list'] = SimpleLazyObject(self._subevent_list_context)
            context['subevent_list_cache_key'] = self._subevent_list_cachekey()

        context['show_cart'] = (
            context['cart']['positions'] and (
                self.request.event.has_subevents or self.request.event.presale_is_running
            )
        )
        if self.request.event.settings.redirect_to_checkout_directly:
            context['cart_redirect'] = eventreverse(self.request.event, 'presale:event.checkout.start',
                                                    kwargs={'cart_namespace': kwargs.get('cart_namespace') or ''})
            if context['cart_redirect'].startswith('https:'):
                context['cart_redirect'] = '/' + context['cart_redirect'].split('/', 3)[3]
        else:
            context['cart_redirect'] = self.request.path

        return context

    def _subevent_list_cachekey(self):
        cache_key_parts = [
            self.request.host,
            str(self.request.event.pk),
            self.request.get_full_path(),
            self.request.LANGUAGE_CODE,
            self.request.sales_channel.identifier,
        ]
        cache_key = f'pretix.presale.views.event.EventIndex.subevent_list_context:{hashlib.md5(":".join(cache_key_parts).encode()).hexdigest()}'
        return cache_key

    def _subevent_list_context(self):
        voucher = None
        if self.request.GET.get('voucher'):
            try:
                voucher = Voucher.objects.get(code__iexact=self.request.GET.get('voucher'), event=self.request.event)
            except Voucher.DoesNotExist:
                pass

        context = {}
        context['list_type'] = self.request.GET.get("style", self.request.event.settings.event_list_type)
        if context['list_type'] not in ("calendar", "week") and self.request.event.subevents.filter(date_from__gt=now()).count() > 50:
            if self.request.event.settings.event_list_type not in ("calendar", "week"):
                self.request.event.settings.event_list_type = "calendar"
            context['list_type'] = "calendar"

        if context['list_type'] == "calendar":
            self._set_month_year()
            tz = self.request.event.timezone
            _, ndays = calendar.monthrange(self.year, self.month)
            before = datetime(self.year, self.month, 1, 0, 0, 0, tzinfo=tz) - timedelta(days=1)
            after = datetime(self.year, self.month, ndays, 0, 0, 0, tzinfo=tz) + timedelta(days=1)

            if self.request.event.settings.event_calendar_future_only:
                limit_before = now().astimezone(tz)
            else:
                limit_before = before

            context['date'] = date(self.year, self.month, 1)
            context['before'] = before
            context['after'] = after

            ebd = defaultdict(list)
            add_subevents_for_days(
                filter_qs_by_attr(
                    self.request.event.subevents_annotated(
                        self.request.sales_channel.identifier,
                        voucher,
                    ).using(settings.DATABASE_REPLICA),
                    self.request
                ),
                limit_before, after, ebd, set(), self.request.event,
                self.kwargs.get('cart_namespace'),
                voucher,
            )

            # Hide names of subevents in event series where it is always the same.  No need to show the name of the museum thousands of times
            # in the calendar. We previously only looked at the current time range for this condition which caused weird side-effects, so we need
            # an extra query to look at the entire series. For performance reasons, we have a limit on how many different names we look at.
            context['show_names'] = sum(len(i) for i in ebd.values() if isinstance(i, list)) < 2 or self.request.event.cache.get_or_set(
                'has_different_subevent_names',
                lambda: len(set(str(n) for n in self.request.event.subevents.order_by().values_list('name', flat=True).annotate(c=Count('*'))[:250])) != 1,
                timeout=120,
            )
            context['weeks'] = weeks_for_template(ebd, self.year, self.month, future_only=self.request.event.settings.event_calendar_future_only)
            context['months'] = [date(self.year, i + 1, 1) for i in range(12)]
            if self.request.event.settings.event_calendar_future_only:
                context['years'] = range(now().year, now().year + 3)
            else:
                context['years'] = range(now().year - 2, now().year + 3)

            context['has_before'], context['has_after'] = has_before_after(
                Event.objects.none(),
                SubEvent.objects.filter(
                    event=self.request.event,
                ),
                before,
                after,
                future_only=self.request.event.settings.event_calendar_future_only
            )
        elif context['list_type'] == "week":
            self._set_week_year()
            tz = self.request.event.timezone
            week = isoweek.Week(self.year, self.week)
            before = datetime(
                week.monday().year, week.monday().month, week.monday().day, 0, 0, 0, tzinfo=tz
            ) - timedelta(days=1)
            after = datetime(
                week.sunday().year, week.sunday().month, week.sunday().day, 0, 0, 0, tzinfo=tz
            ) + timedelta(days=1)

            if self.request.event.settings.event_calendar_future_only:
                limit_before = now().astimezone(tz)
            else:
                limit_before = before

            context['date'] = week.monday()
            context['before'] = before
            context['after'] = after

            ebd = defaultdict(list)
            add_subevents_for_days(
                filter_qs_by_attr(
                    self.request.event.subevents_annotated(
                        self.request.sales_channel.identifier,
                        voucher=voucher,
                    ).using(settings.DATABASE_REPLICA),
                    self.request
                ),
                limit_before, after, ebd, set(), self.request.event,
                self.kwargs.get('cart_namespace'),
                voucher,
            )

            # Hide names of subevents in event series where it is always the same.  No need to show the name of the museum thousands of times
            # in the calendar. We previously only looked at the current time range for this condition which caused weird side-effects, so we need
            # an extra query to look at the entire series. For performance reasons, we have a limit on how many different names we look at.
            context['show_names'] = sum(len(i) for i in ebd.values() if isinstance(i, list)) < 2 or self.request.event.cache.get_or_set(
                'has_different_subevent_names',
                lambda: len(set(str(n) for n in self.request.event.subevents.order_by().values_list('name', flat=True).annotate(c=Count('*'))[:250])) != 1,
                timeout=120,
            )
            context['days'] = days_for_template(ebd, week, future_only=self.request.event.settings.event_calendar_future_only)
            years = (self.year - 1, self.year, self.year + 1)
            weeks = []
            for year in years:
                weeks += [
                    (date_fromisocalendar(year, i + 1, 1), date_fromisocalendar(year, i + 1, 7))
                    for i in range(53 if date(year, 12, 31).isocalendar()[1] == 53 else 52)
                    if not self.request.event.settings.event_calendar_future_only or
                    date_fromisocalendar(year, i + 1, 7) > now().astimezone(tz).replace(tzinfo=None)
                ]
            context['weeks'] = [[w for w in weeks if w[0].year == year] for year in years]
            context['week_format'] = get_format('WEEK_FORMAT')
            if context['week_format'] == 'WEEK_FORMAT':
                context['week_format'] = WEEK_FORMAT
            context['short_month_day_format'] = get_format('SHORT_MONTH_DAY_FORMAT')
            if context['short_month_day_format'] == 'SHORT_MONTH_DAY_FORMAT':
                context['short_month_day_format'] = SHORT_MONTH_DAY_FORMAT

            context['has_before'], context['has_after'] = has_before_after(
                Event.objects.none(),
                SubEvent.objects.filter(
                    event=self.request.event,
                ),
                before,
                after,
                future_only=self.request.event.settings.event_calendar_future_only
            )
        else:
            context['subevent_list'] = self.request.event.subevents_sorted(
                filter_qs_by_attr(
                    self.request.event.subevents_annotated(
                        self.request.sales_channel.identifier,
                        voucher=voucher,
                    ).using(settings.DATABASE_REPLICA),
                    self.request
                )
            )
            if self.request.event.settings.event_list_available_only and not voucher:
                context['subevent_list'] = [
                    se for se in context['subevent_list']
                    if not se.presale_has_ended and (se.best_availability_state is None or se.best_availability_state >= Quota.AVAILABILITY_RESERVED)
                ]
        return context


@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class SeatingPlanView(EventViewMixin, TemplateView):
    template_name = "pretixpresale/event/seatingplan.html"

    def get(self, request, *args, **kwargs):
        from pretix.presale.views.cart import get_or_create_cart_id

        self.subevent = None
        if request.GET.get('src', '') == 'widget' and 'take_cart_id' in request.GET:
            # User has clicked "Open in a new tab" link in widget
            get_or_create_cart_id(request)
            return redirect(eventreverse(request.event, 'presale:event.seatingplan', kwargs=kwargs))
        elif request.GET.get('iframe', '') == '1' and 'take_cart_id' in request.GET:
            # Widget just opened, a cart already exists. Let's to a stupid redirect to check if cookies are disabled
            get_or_create_cart_id(request)
            return redirect(eventreverse(request.event, 'presale:event.seatingplan', kwargs=kwargs) + '?require_cookie=true&cart_id={}'.format(
                request.GET.get('take_cart_id')
            ))
        elif request.GET.get('iframe', '') == '1' and len(self.request.GET.get('widget_data', '{}')) > 3:
            # We've been passed data from a widget, we need to create a cart session to store it.
            get_or_create_cart_id(request)

        if request.event.has_subevents:
            if 'subevent' in kwargs:
                self.subevent = request.event.subevents.using(settings.DATABASE_REPLICA).filter(pk=kwargs['subevent'], active=True).first()
                if not self.subevent or not self.subevent.seating_plan:
                    raise Http404()
                return super().get(request, *args, **kwargs)
            else:
                raise Http404()
        else:
            if 'subevent' in kwargs or not request.event.seating_plan:
                raise Http404()
            else:
                return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['subevent'] = self.subevent
        context['cart_redirect'] = eventreverse(self.request.event, 'presale:event.checkout.start',
                                                kwargs={'cart_namespace': kwargs.get('cart_namespace') or ''})
        if context['cart_redirect'].startswith('https:'):
            context['cart_redirect'] = '/' + context['cart_redirect'].split('/', 3)[3]

        v = self.request.GET.get('voucher')
        if v:
            v = v.strip()
            try:
                voucher = self.request.event.vouchers.get(code__iexact=v)
                if voucher.redeemed >= voucher.max_usages or voucher.valid_until is not None \
                        and voucher.valid_until < now() or voucher.item is not None \
                        and voucher.item.is_available() is False:
                    voucher = None
            except Voucher.DoesNotExist:
                voucher = None
        else:
            voucher = None
        context['voucher'] = voucher

        return context


class EventIcalDownload(EventViewMixin, View):
    def get(self, request, *args, **kwargs):
        if not self.request.event:
            raise Http404(_('Unknown event code or not authorized to access this event.'))

        subevent = None
        if request.event.has_subevents:
            if 'subevent' in kwargs:
                subevent = get_object_or_404(SubEvent, event=request.event, pk=kwargs['subevent'], active=True)
            else:
                raise Http404(pgettext_lazy('subevent', 'No date selected.'))
        else:
            if 'subevent' in kwargs:
                raise Http404(pgettext_lazy('subevent', 'Unknown date selected.'))

        event = self.request.event
        cal = get_public_ical([subevent or event])

        resp = HttpResponse(cal.serialize(), content_type='text/calendar')
        resp['Content-Disposition'] = 'attachment; filename="{}-{}-{}.ics"'.format(
            event.organizer.slug, event.slug, subevent.pk if subevent else '0',
        )
        if event.settings.meta_noindex:
            resp['X-Robots-Tag'] = 'noindex'
        return resp


class EventAuth(View):
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        s = SessionStore(request.POST.get('session'))

        try:
            data = s.load()
        except:
            raise PermissionDenied(_('Please go back and try again.'))

        parent = data.get('pretix_event_access_{}'.format(request.event.pk))

        sparent = SessionStore(parent)
        try:
            parentdata = sparent.load()
        except:
            raise PermissionDenied(_('Please go back and try again.'))
        else:
            if 'event_access' not in parentdata:
                raise PermissionDenied(_('Please go back and try again.'))

        request.session['pretix_event_access_{}'.format(request.event.pk)] = parent
        return redirect(eventreverse(request.event, 'presale:event.index'))
