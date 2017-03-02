import sys
from datetime import datetime
from importlib import import_module

import pytz
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView
from icalendar import Calendar, Event
from pytz import timezone

from pretix.base.models import ItemVariation
from pretix.multidomain.urlreverse import eventreverse

from . import CartMixin, EventViewMixin

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


def get_grouped_items(event):
    items = event.items.all().filter(
        Q(active=True)
        & Q(Q(available_from__isnull=True) | Q(available_from__lte=now()))
        & Q(Q(available_until__isnull=True) | Q(available_until__gte=now()))
        & Q(hide_without_voucher=False)
    ).select_related(
        'category',  # for re-grouping
    ).prefetch_related(
        'variations__quotas',  # for .availability()
        Prefetch('quotas',
                 queryset=event.quotas.all()),
        Prefetch('variations', to_attr='available_variations',
                 queryset=ItemVariation.objects.filter(active=True, quotas__isnull=False).distinct()),
    ).annotate(
        quotac=Count('quotas'),
        has_variations=Count('variations')
    ).filter(
        quotac__gt=0
    ).order_by('category__position', 'category_id', 'position', 'name')
    display_add_to_cart = False
    quota_cache = {}
    for item in items:
        if not item.has_variations:
            item.cached_availability = list(item.check_quotas(_cache=quota_cache))
            item.order_max = min(item.cached_availability[1]
                                 if item.cached_availability[1] is not None else sys.maxsize,
                                 int(event.settings.max_items_per_order))
            item.price = item.default_price
            item.display_price = item.default_price_net if event.settings.display_net_prices else item.price
            display_add_to_cart = display_add_to_cart or item.order_max > 0
        else:
            for var in item.available_variations:
                var.cached_availability = list(var.check_quotas(_cache=quota_cache))
                var.order_max = min(var.cached_availability[1]
                                    if var.cached_availability[1] is not None else sys.maxsize,
                                    int(event.settings.max_items_per_order))
                var.display_price = var.net_price if event.settings.display_net_prices else var.price
                display_add_to_cart = display_add_to_cart or var.order_max > 0
            if len(item.available_variations) > 0:
                item.min_price = min([v.display_price for v in item.available_variations])
                item.max_price = max([v.display_price for v in item.available_variations])

    items = [item for item in items if len(item.available_variations) > 0 or not item.has_variations]
    return items, display_add_to_cart


class EventIndex(EventViewMixin, CartMixin, TemplateView):
    template_name = "pretixpresale/event/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch all items
        items, display_add_to_cart = get_grouped_items(self.request.event)

        # Regroup those by category
        context['items_by_category'] = item_group_by_category(items)
        context['display_add_to_cart'] = display_add_to_cart

        vouchers_exist = self.request.event.get_cache().get('vouchers_exist')
        if vouchers_exist is None:
            vouchers_exist = self.request.event.vouchers.exists()
            self.request.event.get_cache().set('vouchers_exist', vouchers_exist)
        context['vouchers_exist'] = vouchers_exist

        context['cart'] = self.get_cart()

        context['frontpage_text'] = str(self.request.event.settings.frontpage_text)
        return context


class EventIcalDownload(EventViewMixin, View):

    @cached_property
    def event_timezone(self):
        return timezone(self.request.event.settings.timezone)

    def get(self, request, *args, **kwargs):
        if not self.request.event:
            raise Http404(_('Unknown event code or not authorized to access this event.'))

        cal = Calendar()
        cal.add('version', '2.0')
        cal.add('prodid', '-//pretix//{}//'.format(settings.PRETIX_INSTANCE_NAME))

        event = Event()
        event.add('summary', str(self.request.event.name))
        event.add('dtstamp', datetime.now(pytz.utc))
        event.add('location', str(self.request.event.location))
        event.add('organizer', self.request.event.organizer.name)

        if self.request.event.settings.show_times:
            event.add('dtstart', self.request.event.date_from.replace(tzinfo=self.event_timezone))
        else:
            event.add('dtstart', self.request.event.date_from.date())

        if self.request.event.settings.show_date_to:
            if self.request.event.settings.show_times:
                event.add('dtend', self.request.event.date_to.replace(tzinfo=self.event_timezone))
            else:
                event.add('dtend', self.request.event.date_to.date())

        cal.add_component(event)

        resp = HttpResponse(cal.to_ical(), content_type='text/calendar')
        resp['Content-Disposition'] = 'attachment; filename="pretixevent.ics"'
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
