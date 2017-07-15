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
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from pretix.base.decimal import round_decimal
from pretix.base.models import ItemVariation
from pretix.base.models.event import SubEvent
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.ical import get_ical
from pretix.presale.views.organizer import (
    add_subevents_for_days, weeks_for_template,
)

from . import CartMixin, EventViewMixin, get_cart

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


def get_grouped_items(event, subevent=None):
    items = event.items.all().filter(
        Q(active=True)
        & Q(Q(available_from__isnull=True) | Q(available_from__lte=now()))
        & Q(Q(available_until__isnull=True) | Q(available_until__gte=now()))
        & Q(hide_without_voucher=False)
        & ~Q(category__is_addon=True)
    ).select_related(
        'category',  # for re-grouping
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
    quota_cache = {}

    if subevent:
        item_price_override = subevent.item_price_overrides
        var_price_override = subevent.var_price_overrides
    else:
        item_price_override = {}
        var_price_override = {}

    for item in items:
        max_per_order = item.max_per_order or int(event.settings.max_items_per_order)
        if not item.has_variations:
            item._remove = not bool(item._subevent_quotas)
            item.cached_availability = list(item.check_quotas(subevent=subevent, _cache=quota_cache))
            item.order_max = min(item.cached_availability[1]
                                 if item.cached_availability[1] is not None else sys.maxsize,
                                 max_per_order)
            item.price = item.default_price

            if event.settings.display_net_prices:
                if item_price_override.get(item.pk):
                    _p = item_price_override.get(item.pk)
                    tax_value = round_decimal(_p * (1 - 100 / (100 + item.tax_rate)))
                    item.display_price = _p - tax_value
                else:
                    item.display_price = item.default_price_net
            else:
                item.display_price = item_price_override.get(item.pk, item.price)
            display_add_to_cart = display_add_to_cart or item.order_max > 0
        else:
            for var in item.available_variations:
                var.cached_availability = list(var.check_quotas(subevent=subevent, _cache=quota_cache))
                var.order_max = min(var.cached_availability[1]
                                    if var.cached_availability[1] is not None else sys.maxsize,
                                    max_per_order)

                if event.settings.display_net_prices:
                    if var_price_override.get(var.pk):
                        _p = var_price_override.get(var.pk)
                        tax_value = round_decimal(_p * (1 - 100 / (100 + item.tax_rate)))
                        var.display_price = _p - tax_value
                    else:
                        var.display_price = var.net_price
                else:
                    var.display_price = var_price_override.get(var.pk, var.price)

                display_add_to_cart = display_add_to_cart or var.order_max > 0

            item.available_variations = [
                v for v in item.available_variations if v._subevent_quotas
            ]
            if len(item.available_variations) > 0:
                item.min_price = min([v.display_price for v in item.available_variations])
                item.max_price = max([v.display_price for v in item.available_variations])
            item._remove = not bool(item.available_variations)

    items = [item for item in items
             if (len(item.available_variations) > 0 or not item.has_variations) and not item._remove]
    return items, display_add_to_cart


class EventIndex(EventViewMixin, CartMixin, TemplateView):
    template_name = "pretixpresale/event/index.html"

    def get(self, request, *args, **kwargs):
        self.subevent = None
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
                return redirect(eventreverse(request.event, 'presale:event.index'))
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

            # Regroup those by category
            context['items_by_category'] = item_group_by_category(items)
            context['display_add_to_cart'] = display_add_to_cart

        context['subevent'] = self.subevent
        context['cart'] = self.get_cart()
        context['has_addon_choices'] = get_cart(self.request).filter(item__addons__isnull=False).exists()
        vouchers_exist = self.request.event.get_cache().get('vouchers_exist')
        if vouchers_exist is None:
            vouchers_exist = self.request.event.vouchers.exists()
            self.request.event.get_cache().set('vouchers_exist', vouchers_exist)
        context['vouchers_exist'] = vouchers_exist
        context['ev'] = self.subevent or self.request.event
        if self.subevent:
            context['frontpage_text'] = str(self.subevent.frontpage_text)
        else:
            context['frontpage_text'] = str(self.request.event.settings.frontpage_text)

        if self.request.event.settings.event_list_type == "calendar":
            self._set_month_year()
            tz = pytz.timezone(self.request.event.settings.timezone)
            _, ndays = calendar.monthrange(self.year, self.month)
            before = datetime(self.year, self.month, 1, 0, 0, 0, tzinfo=tz) - timedelta(days=1)
            after = datetime(self.year, self.month, ndays, 0, 0, 0, tzinfo=tz) + timedelta(days=1)

            context['date'] = date(self.year, self.month, 1)
            context['before'] = before
            context['after'] = after

            ebd = defaultdict(list)
            add_subevents_for_days(self.request.event.subevents.all(), before, after, ebd, set(), self.request.event)

            context['weeks'] = weeks_for_template(ebd, self.year, self.month)
            context['months'] = [date(self.year, i + 1, 1) for i in range(12)]
            context['years'] = range(now().year - 2, now().year + 3)

        context['show_cart'] = (
            context['cart']['positions'] and (
                self.request.event.has_subevents or self.request.event.presale_is_running
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
