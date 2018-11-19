import calendar
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from importlib import import_module

import pytz
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from pretix.base.models import ItemVariation, Quota
from pretix.base.models.event import SubEvent
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.ical import get_ical
from pretix.presale.views.organizer import (
    add_subevents_for_days, weeks_for_template,
)

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


def get_grouped_items(event, subevent=None, voucher=None):
    items = event.items.all().filter(
        Q(active=True)
        & Q(Q(available_from__isnull=True) | Q(available_from__lte=now()))
        & Q(Q(available_until__isnull=True) | Q(available_until__gte=now()))
        & Q(Q(category__isnull=True) | Q(category__is_addon=False))
    )

    vouchq = Q(hide_without_voucher=False)
    if voucher:
        if voucher.item_id:
            vouchq |= Q(pk=voucher.item_id)
            items = items.filter(pk=voucher.item_id)
        elif voucher.quota_id:
            items = items.filter(quotas__in=[voucher.quota_id])

    items = items.filter(vouchq).select_related(
        'category', 'tax_rule',  # for re-grouping
    ).prefetch_related(
        Prefetch('quotas',
                 to_attr='_subevent_quotas',
                 queryset=event.quotas.filter(subevent=subevent)),
        Prefetch('variations', to_attr='available_variations',
                 queryset=ItemVariation.objects.filter(active=True, quotas__isnull=False).prefetch_related(
                     Prefetch('quotas',
                              to_attr='_subevent_quotas',
                              queryset=event.quotas.filter(subevent=subevent))
                 ).distinct()),
    ).annotate(
        quotac=Count('quotas'),
        has_variations=Count('variations')
    ).filter(
        quotac__gt=0
    ).order_by('category__position', 'category_id', 'position', 'name')
    display_add_to_cart = False
    external_quota_cache = event.cache.get('item_quota_cache')
    quota_cache = external_quota_cache or {}

    if subevent:
        item_price_override = subevent.item_price_overrides
        var_price_override = subevent.var_price_overrides
    else:
        item_price_override = {}
        var_price_override = {}

    for item in items:
        if voucher and voucher.item_id and voucher.variation_id:
            # Restrict variations if the voucher only allows one
            item.available_variations = [v for v in item.available_variations
                                         if v.pk == voucher.variation_id]

        max_per_order = item.max_per_order or int(event.settings.max_items_per_order)

        if not item.has_variations:
            item._remove = not bool(item._subevent_quotas)

            if voucher and (voucher.allow_ignore_quota or voucher.block_quota):
                item.cached_availability = (
                    Quota.AVAILABILITY_OK, voucher.max_usages - voucher.redeemed
                )
            else:
                item.cached_availability = list(
                    item.check_quotas(subevent=subevent, _cache=quota_cache)
                )

            item.order_max = min(
                item.cached_availability[1]
                if item.cached_availability[1] is not None else sys.maxsize,
                max_per_order
            )

            price = item_price_override.get(item.pk, item.default_price)
            if voucher:
                price = voucher.calculate_price(price)
            item.display_price = item.tax(price)

            display_add_to_cart = display_add_to_cart or item.order_max > 0
        else:
            for var in item.available_variations:
                if voucher and (voucher.allow_ignore_quota or voucher.block_quota):
                    var.cached_availability = (
                        Quota.AVAILABILITY_OK, voucher.max_usages - voucher.redeemed
                    )
                else:
                    var.cached_availability = list(
                        var.check_quotas(subevent=subevent, _cache=quota_cache)
                    )

                var.order_max = min(
                    var.cached_availability[1]
                    if var.cached_availability[1] is not None else sys.maxsize,
                    max_per_order
                )

                price = var_price_override.get(var.pk, var.price)
                if voucher:
                    price = voucher.calculate_price(price)
                var.display_price = var.tax(price)

                display_add_to_cart = display_add_to_cart or var.order_max > 0

            item.available_variations = [
                v for v in item.available_variations if v._subevent_quotas
            ]
            if voucher and voucher.variation_id:
                item.available_variations = [v for v in item.available_variations
                                             if v.pk == voucher.variation_id]

            if len(item.available_variations) > 0:
                item.min_price = min([v.display_price.net if event.settings.display_net_prices else
                                      v.display_price.gross for v in item.available_variations])
                item.max_price = max([v.display_price.net if event.settings.display_net_prices else
                                      v.display_price.gross for v in item.available_variations])

            item._remove = not bool(item.available_variations)

    if not external_quota_cache:
        event.cache.set('item_quota_cache', quota_cache, 5)
    items = [item for item in items
             if (len(item.available_variations) > 0 or not item.has_variations) and not item._remove]
    return items, display_add_to_cart


@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class EventIndex(EventViewMixin, CartMixin, TemplateView):
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
                self.subevent = request.event.subevents.filter(pk=kwargs['subevent'], active=True).first()
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

    def _set_month_year(self):
        tz = pytz.timezone(self.request.event.settings.timezone)
        if self.subevent:
            self.year = self.subevent.date_from.astimezone(tz).year
            self.month = self.subevent.date_from.astimezone(tz).month
        elif 'year' in self.request.GET and 'month' in self.request.GET:
            try:
                self.year = int(self.request.GET.get('year'))
                self.month = int(self.request.GET.get('month'))
            except ValueError:
                self.year = now().year
                self.month = now().month
        else:
            next_sev = self.request.event.subevents.filter(
                active=True,
                date_from__gte=now()
            ).select_related('event').order_by('date_from').first()

            if next_sev:
                datetime_from = next_sev.date_from
                self.year = datetime_from.astimezone(tz).year
                self.month = datetime_from.astimezone(tz).month
            else:
                self.year = now().year
                self.month = now().month

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not self.request.event.has_subevents or self.subevent:
            # Fetch all items
            items, display_add_to_cart = get_grouped_items(self.request.event, self.subevent)
            context['itemnum'] = len(items)

            # Regroup those by category
            context['items_by_category'] = item_group_by_category(items)
            context['display_add_to_cart'] = display_add_to_cart

            # Show voucher option if an event is selected and vouchers exist
            vouchers_exist = self.request.event.cache.get('vouchers_exist')
            if vouchers_exist is None:
                vouchers_exist = self.request.event.vouchers.exists()
                self.request.event.cache.set('vouchers_exist', vouchers_exist)
            context['show_vouchers'] = vouchers_exist
        else:
            context['show_vouchers'] = False

        context['ev'] = self.subevent or self.request.event
        context['subevent'] = self.subevent
        context['cart'] = self.get_cart()
        context['has_addon_choices'] = get_cart(self.request).filter(item__addons__isnull=False).exists()

        if self.subevent:
            context['frontpage_text'] = str(self.subevent.frontpage_text)
        else:
            context['frontpage_text'] = str(self.request.event.settings.frontpage_text)

        context['list_type'] = self.request.GET.get("style", self.request.event.settings.event_list_type)

        if context['list_type'] == "calendar":
            self._set_month_year()
            tz = pytz.timezone(self.request.event.settings.timezone)
            _, ndays = calendar.monthrange(self.year, self.month)
            before = datetime(self.year, self.month, 1, 0, 0, 0, tzinfo=tz) - timedelta(days=1)
            after = datetime(self.year, self.month, ndays, 0, 0, 0, tzinfo=tz) + timedelta(days=1)

            context['date'] = date(self.year, self.month, 1)
            context['before'] = before
            context['after'] = after

            ebd = defaultdict(list)
            add_subevents_for_days(self.request.event.subevents.all(), before, after, ebd, set(), self.request.event,
                                   kwargs.get('cart_namespace'))

            context['weeks'] = weeks_for_template(ebd, self.year, self.month)
            context['months'] = [date(self.year, i + 1, 1) for i in range(12)]
            context['years'] = range(now().year - 2, now().year + 3)

        context['show_cart'] = (
            context['cart']['positions'] and (
                self.request.event.has_subevents or self.request.event.presale_is_running
            )
        )
        context['show_dates'] = (
            self.request.event.has_subevents and (
                'cart_namespace' not in self.kwargs
                or not self.subevent
            )
        )

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
