import sys
from datetime import datetime
from importlib import import_module

import pytz
import vobject
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView
from pytz import timezone

from pretix.base.decimal import round_decimal
from pretix.base.models import ItemVariation
from pretix.base.models.event import SubEvent
from pretix.multidomain.urlreverse import eventreverse

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
                self.subevent = get_object_or_404(SubEvent, event=request.event, pk=kwargs['subevent'], active=True)
                return super().get(request, *args, **kwargs)
            else:
                return super().get(request, *args, **kwargs)
        else:
            if 'subevent' in kwargs:
                return redirect(eventreverse(request.event, 'presale:event.index'))
            else:
                return super().get(request, *args, **kwargs)

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
        context['frontpage_text'] = str(self.request.event.settings.frontpage_text)
        return context


class EventIcalDownload(EventViewMixin, View):

    @cached_property
    def event_timezone(self):
        return timezone(self.request.event.settings.timezone)

    def get(self, request, *args, **kwargs):
        if not self.request.event:
            raise Http404(_('Unknown event code or not authorized to access this event.'))

        event = self.request.event
        creation_time = datetime.now(pytz.utc)
        cal = vobject.iCalendar()
        cal.add('prodid').value = '-//pretix//{}//'.format(settings.PRETIX_INSTANCE_NAME)

        vevent = cal.add('vevent')
        vevent.add('summary').value = str(event.name)
        vevent.add('dtstamp').value = creation_time
        vevent.add('location').value = str(event.location)
        vevent.add('organizer').value = event.organizer.name
        vevent.add('uid').value = '{}-{}-{}'.format(
            event.organizer.slug, event.slug, creation_time.strftime('%Y%m%d%H%M%S%f')
        )

        if event.settings.show_times:
            vevent.add('dtstart').value = event.date_from.astimezone(self.event_timezone)
        else:
            vevent.add('dtstart').value = event.date_from.astimezone(self.event_timezone).date()

        if event.settings.show_date_to:
            if event.settings.show_times:
                vevent.add('dtend').value = event.date_to.astimezone(self.event_timezone)
            else:
                vevent.add('dtend').value = event.date_to.astimezone(self.event_timezone).date()

        if event.date_admission:
            vevent.add('description').value = str(_('Admission: {datetime}')).format(
                datetime=date_format(event.date_admission.astimezone(self.event_timezone), 'SHORT_DATETIME_FORMAT')
            )

        resp = HttpResponse(cal.serialize(), content_type='text/calendar')
        resp['Content-Disposition'] = 'attachment; filename="{}-{}.ics"'.format(
            event.organizer.slug, event.slug
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
