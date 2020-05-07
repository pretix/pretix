import calendar
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from importlib import import_module

import isoweek
import pytz
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Exists, OuterRef, Prefetch
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.formats import get_format
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from pretix.base.channels import get_all_sales_channels
from pretix.base.models import ItemVariation, Quota, SeatCategoryMapping
from pretix.base.models.event import SubEvent
from pretix.base.models.items import ItemBundle
from pretix.base.services.quotas import QuotaAvailability
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.ical import get_ical
from pretix.presale.signals import item_description
from pretix.presale.views.organizer import (
    EventListMixin, add_subevents_for_days, days_for_template,
    filter_qs_by_attr, weeks_for_template,
)

from ...helpers.formats.en.formats import WEEK_FORMAT
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


def get_grouped_items(event, subevent=None, voucher=None, channel='web', require_seat=0, base_qs=None):
    base_qs = base_qs if base_qs is not None else event.items
    items = base_qs.using(settings.DATABASE_REPLICA).filter_available(channel=channel, voucher=voucher).select_related(
        'category', 'tax_rule',  # for re-grouping
        'hidden_if_available',
    ).prefetch_related(
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
                 queryset=ItemVariation.objects.using(settings.DATABASE_REPLICA).filter(active=True, quotas__isnull=False).prefetch_related(
                     Prefetch('quotas',
                              to_attr='_subevent_quotas',
                              queryset=event.quotas.using(settings.DATABASE_REPLICA).filter(subevent=subevent))
                 ).distinct()),
    ).annotate(
        quotac=Count('quotas'),
        has_variations=Count('variations'),
        requires_seat=Exists(
            SeatCategoryMapping.objects.filter(
                product_id=OuterRef('pk'),
                subevent=subevent
            )
        )
    ).filter(
        quotac__gt=0,
    ).order_by('category__position', 'category_id', 'position', 'name')
    if require_seat:
        items = items.filter(requires_seat__gt=0)
    else:
        items = items.filter(requires_seat=0)
    display_add_to_cart = False
    external_quota_cache = event.cache.get('item_quota_cache')
    quota_cache = external_quota_cache or {}

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
                    if q not in quota_cache:
                        quotas_to_compute.append(q)
        else:
            for q in item._subevent_quotas:
                if q not in quota_cache:
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

            if event.settings.hide_sold_out and item.cached_availability[0] < Quota.AVAILABILITY_RESERVED:
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

            display_add_to_cart = display_add_to_cart or item.order_max > 0
        else:
            for var in item.available_variations:
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

                display_add_to_cart = display_add_to_cart or var.order_max > 0

            item.original_price = (
                item.tax(item.original_price, currency=event.currency, include_bundled=True,
                         base_price_is='net' if event.settings.display_net_prices else 'gross')  # backwards-compat
                if item.original_price else None
            )

            item.available_variations = [
                v for v in item.available_variations if v._subevent_quotas and (
                    not voucher or not voucher.quota_id or v in restrict_vars
                )
            ]

            if event.settings.hide_sold_out:
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

            item._remove = not bool(item.available_variations)

    if not external_quota_cache and not voucher:
        event.cache.set('item_quota_cache', quota_cache, 5)
    items = [item for item in items
             if (len(item.available_variations) > 0 or not item.has_variations) and not item._remove]
    return items, display_add_to_cart


@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class EventIndex(EventViewMixin, EventListMixin, CartMixin, TemplateView):
    template_name = "pretixpresale/event/index.html"

    def get(self, request, *args, **kwargs):
        from pretix.presale.views.cart import get_or_create_cart_id

        self.subevent = None
        if request.GET.get('src', '') == 'widget' and 'take_cart_id' in request.GET:
            # User has clicked "Open in a new tab" link in widget
            get_or_create_cart_id(request)
            return redirect(eventreverse(request.event, 'presale:event.index', kwargs=kwargs))
        elif request.GET.get('iframe', '') == '1' and 'take_cart_id' in request.GET:
            # Widget just opened, a cart already exists. Let's to a stupid redirect to check if cookies are disabled
            get_or_create_cart_id(request)
            return redirect(eventreverse(request.event, 'presale:event.index', kwargs=kwargs) + '?require_cookie=true&cart_id={}'.format(
                request.GET.get('take_cart_id')
            ))
        elif request.GET.get('iframe', '') == '1' and len(self.request.GET.get('widget_data', '{}')) > 3:
            # We've been passed data from a widget, we need to create a cart session to store it.
            get_or_create_cart_id(request)
        elif 'require_cookie' in request.GET and settings.SESSION_COOKIE_NAME not in request.COOKIES:
            # Cookies are in fact not supported
            r = render(request, 'pretixpresale/event/cookies.html', {
                'url': eventreverse(
                    request.event, "presale:event.index", kwargs={'cart_namespace': kwargs.get('cart_namespace') or ''}
                ) + (
                    "?src=widget&take_cart_id={}".format(request.GET.get('cart_id'))
                    if "cart_id" in request.GET else ""
                )
            })
            r._csp_ignore = True
            return r

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

        # Show voucher option if an event is selected and vouchers exist
        vouchers_exist = self.request.event.cache.get('vouchers_exist')
        if vouchers_exist is None:
            vouchers_exist = self.request.event.vouchers.exists()
            self.request.event.cache.set('vouchers_exist', vouchers_exist)

        if not self.request.event.has_subevents or self.subevent:
            # Fetch all items
            items, display_add_to_cart = get_grouped_items(self.request.event, self.subevent,
                                                           channel=self.request.sales_channel.identifier)
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

            context['show_vouchers'] = vouchers_exist
            context['vouchers_exist'] = vouchers_exist
        else:
            context['show_vouchers'] = False
            context['vouchers_exist'] = vouchers_exist

        context['ev'] = self.subevent or self.request.event
        context['subevent'] = self.subevent
        context['cart'] = self.get_cart()
        context['has_addon_choices'] = get_cart(self.request).filter(item__addons__isnull=False).exists()

        if self.subevent:
            context['frontpage_text'] = str(self.subevent.frontpage_text)
        else:
            context['frontpage_text'] = str(self.request.event.settings.frontpage_text)

        context['list_type'] = self.request.GET.get("style", self.request.event.settings.event_list_type)
        if context['list_type'] not in ("calendar", "week") and self.request.event.subevents.count() > 100:
            if self.request.event.settings.event_list_type not in ("calendar", "week"):
                self.request.event.settings.event_list_type = "calendar"
            context['list_type'] = "calendar"

        if context['list_type'] == "calendar" and self.request.event.has_subevents:
            self._set_month_year()
            tz = pytz.timezone(self.request.event.settings.timezone)
            _, ndays = calendar.monthrange(self.year, self.month)
            before = datetime(self.year, self.month, 1, 0, 0, 0, tzinfo=tz) - timedelta(days=1)
            after = datetime(self.year, self.month, ndays, 0, 0, 0, tzinfo=tz) + timedelta(days=1)

            context['date'] = date(self.year, self.month, 1)
            context['before'] = before
            context['after'] = after

            ebd = defaultdict(list)
            add_subevents_for_days(
                filter_qs_by_attr(self.request.event.subevents_annotated(self.request.sales_channel.identifier).using(settings.DATABASE_REPLICA), self.request),
                before, after, ebd, set(), self.request.event,
                kwargs.get('cart_namespace')
            )

            context['weeks'] = weeks_for_template(ebd, self.year, self.month)
            context['months'] = [date(self.year, i + 1, 1) for i in range(12)]
            context['years'] = range(now().year - 2, now().year + 3)
        elif context['list_type'] == "week" and self.request.event.has_subevents:
            self._set_month_week()
            tz = pytz.timezone(self.request.event.settings.timezone)
            week = isoweek.Week(self.year, self.week)
            before = datetime(
                week.monday().year, week.monday().month, week.monday().day, 0, 0, 0, tzinfo=tz
            ) - timedelta(days=1)
            after = datetime(
                week.sunday().year, week.sunday().month, week.sunday().day, 0, 0, 0, tzinfo=tz
            ) + timedelta(days=1)

            context['date'] = week.monday()
            context['before'] = before
            context['after'] = after

            ebd = defaultdict(list)
            add_subevents_for_days(
                filter_qs_by_attr(self.request.event.subevents_annotated(self.request.sales_channel.identifier).using(settings.DATABASE_REPLICA), self.request),
                before, after, ebd, set(), self.request.event,
                kwargs.get('cart_namespace')
            )

            context['days'] = days_for_template(ebd, week)
            context['weeks'] = [date(self.year, i + 1, 1) for i in range(12)]
            context['weeks'] = [i + 1 for i in range(53)]
            context['years'] = range(now().year - 2, now().year + 3)
            context['week_format'] = get_format('WEEK_FORMAT')
            if context['week_format'] == 'WEEK_FORMAT':
                context['week_format'] = WEEK_FORMAT
            context['day_format'] = get_format('WEEK_DAY_FORMAT')
            if context['day_format'] == 'WEEK_DAY_FORMAT':
                context['day_format'] = 'SHORT_DATE_FORMAT'
        elif self.request.event.has_subevents:
            context['subevent_list'] = self.request.event.subevents_sorted(
                filter_qs_by_attr(self.request.event.subevents_annotated(self.request.sales_channel.identifier).using(settings.DATABASE_REPLICA), self.request)
            )

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
        cal = get_ical([subevent or event])

        resp = HttpResponse(cal.serialize(), content_type='text/calendar')
        resp['Content-Disposition'] = 'attachment; filename="{}-{}-{}.ics"'.format(
            event.organizer.slug, event.slug, subevent.pk if subevent else '0',
        )
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
