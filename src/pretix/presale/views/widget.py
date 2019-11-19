import calendar
import hashlib
import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

import pytz
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.template import Context, Engine
from django.template.loader import get_template
from django.utils.formats import date_format
from django.utils.timezone import now
from django.utils.translation import get_language, pgettext, ugettext
from django.utils.translation.trans_real import DjangoTranslation
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.decorators.http import condition
from django.views.i18n import (
    JavaScriptCatalog, get_formats, js_catalog_template,
)
from lxml import etree

from pretix.base.i18n import language
from pretix.base.models import CartPosition, Event, Quota, SubEvent, Voucher
from pretix.base.services.cart import error_messages
from pretix.base.settings import GlobalSettingsObject
from pretix.base.templatetags.rich_text import rich_text
from pretix.helpers.daterange import daterange
from pretix.helpers.thumb import get_thumbnail
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.presale.views.cart import get_or_create_cart_id
from pretix.presale.views.event import (
    get_grouped_items, item_group_by_category,
)
from pretix.presale.views.organizer import (
    EventListMixin, add_events_for_days, add_subevents_for_days,
    filter_qs_by_attr, weeks_for_template,
)

logger = logging.getLogger(__name__)


def indent(s):
    return s.replace('\n', '\n  ')


def widget_css_etag(request, **kwargs):
    o = getattr(request, 'event', request.organizer)
    return o.settings.presale_widget_css_checksum or o.settings.presale_widget_css_checksum


def widget_js_etag(request, lang, **kwargs):
    gs = GlobalSettingsObject()
    return gs.settings.get('widget_checksum_{}'.format(lang))


@condition(etag_func=widget_css_etag)
@cache_page(60)
def widget_css(request, **kwargs):
    o = getattr(request, 'event', request.organizer)
    if o.settings.presale_widget_css_file:
        resp = FileResponse(default_storage.open(o.settings.presale_widget_css_file),
                            content_type='text/css')
        return resp
    else:
        tpl = get_template('pretixpresale/widget_dummy.html')
        et = etree.fromstring(tpl.render({})).attrib['href'].replace(settings.STATIC_URL, '')
        f = finders.find(et)
        resp = FileResponse(open(f, 'rb'), content_type='text/css')
        return resp


def generate_widget_js(lang):
    code = []
    with language(lang):
        # Provide isolation
        code.append('(function (siteglobals) {\n')
        code.append('var module = {}, exports = {};\n')
        code.append('var lang = "%s";\n' % lang)

        c = JavaScriptCatalog()
        c.translation = DjangoTranslation(lang, domain='djangojs')
        catalog, plural = c.get_catalog(), c.get_plural()

        str_wl = (
            'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su',
            'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
            'September', 'October', 'November', 'December'
        )
        catalog = dict((k, v) for k, v in catalog.items() if k.startswith('widget\u0004') or k in str_wl)
        template = Engine().from_string(js_catalog_template)
        context = Context({
            'catalog_str': indent(json.dumps(
                catalog, sort_keys=True, indent=2)) if catalog else None,
            'formats_str': indent(json.dumps(
                get_formats(), sort_keys=True, indent=2)),
            'plural': plural,
        })
        code.append(template.render(context))

        files = [
            'vuejs/vue.js' if settings.DEBUG else 'vuejs/vue.min.js',
            'vuejs/vue-resize.min.js',
            'pretixpresale/js/widget/docready.js',
            'pretixpresale/js/widget/floatformat.js',
            'pretixpresale/js/widget/widget.js',
        ]
        for fname in files:
            f = finders.find(fname)
            with open(f, 'r', encoding='utf-8') as fp:
                code.append(fp.read())

        if settings.DEBUG:
            code.append('})(this);\n')
        else:
            # Do not expose debugging variables
            code.append('})({});\n')
    return ''.join(code)


@condition(etag_func=widget_js_etag)
@cache_page(1 if settings.DEBUG else 60)
def widget_js(request, lang, **kwargs):
    if lang not in [lc for lc, ll in settings.LANGUAGES]:
        raise Http404()

    gs = GlobalSettingsObject()
    fname = gs.settings.get('widget_file_{}'.format(lang))
    resp = None
    if fname and not settings.DEBUG:
        try:
            resp = HttpResponse(default_storage.open(fname).read(), content_type='text/javascript')
        except:
            logger.exception('Failed to open widget.js')

    if not resp:
        data = generate_widget_js(lang).encode()
        checksum = hashlib.sha1(data).hexdigest()
        if not settings.DEBUG:
            newname = default_storage.save(
                'widget/widget.{}.{}.js'.format(lang, checksum),
                ContentFile(data)
            )
            gs.settings.set('widget_file_{}'.format(lang), 'file://' + newname)
            gs.settings.set('widget_checksum_{}'.format(lang), checksum)
        resp = HttpResponse(data, content_type='text/javascript')
    return resp


def price_dict(item, price):
    return {
        'gross': price.gross,
        'net': price.net,
        'tax': price.tax,
        'rate': price.rate,
        'name': str(price.name),
        'includes_mixed_tax_rate': item.includes_mixed_tax_rate,
    }


def get_picture(event, picture):
    return urljoin(build_absolute_uri(event, 'presale:event.index'), get_thumbnail(picture.name, '60x60^').thumb.url)


class WidgetAPIProductList(EventListMixin, View):

    def _get_items(self):
        items, display_add_to_cart = get_grouped_items(
            self.request.event, subevent=self.subevent, voucher=self.voucher, channel='web'
        )
        grps = []
        for cat, g in item_group_by_category(items):
            grps.append({
                'id': cat.pk if cat else None,
                'name': str(cat.name) if cat else None,
                'description': str(rich_text(cat.description, safelinks=False)) if cat and cat.description else None,
                'items': [
                    {
                        'id': item.pk,
                        'name': str(item.name),
                        'picture': get_picture(self.request.event, item.picture) if item.picture else None,
                        'description': str(rich_text(item.description, safelinks=False)) if item.description else None,
                        'has_variations': item.has_variations,
                        'require_voucher': item.require_voucher,
                        'order_min': item.min_per_order,
                        'order_max': item.order_max if not item.has_variations else None,
                        'price': price_dict(item, item.display_price) if not item.has_variations else None,
                        'min_price': item.min_price if item.has_variations else None,
                        'max_price': item.max_price if item.has_variations else None,
                        'free_price': item.free_price,
                        'avail': [
                            item.cached_availability[0],
                            item.cached_availability[1] if item.do_show_quota_left else None
                        ] if not item.has_variations else None,
                        'original_price': (
                            (item.original_price.net
                             if self.request.event.settings.display_net_prices
                             else item.original_price.gross)
                            if item.original_price else None
                        ),
                        'variations': [
                            {
                                'id': var.id,
                                'value': str(var.value),
                                'order_max': var.order_max,
                                'description': str(rich_text(var.description, safelinks=False)) if var.description else None,
                                'price': price_dict(item, var.display_price),
                                'original_price': (
                                    (
                                        var.original_price.net
                                        if self.request.event.settings.display_net_prices
                                        else var.original_price.gross
                                    ) if var.original_price else None
                                ) or (
                                    (
                                        item.original_price.net
                                        if self.request.event.settings.display_net_prices
                                        else item.original_price.gross
                                    ) if item.original_price else None
                                ),
                                'avail': [
                                    var.cached_availability[0],
                                    var.cached_availability[1] if item.do_show_quota_left else None
                                ],
                            } for var in item.available_variations
                        ]

                    } for item in g
                ]
            })
        return grps, display_add_to_cart, len(items)

    def post_process(self, data):
        data['poweredby'] = '<a href="https://pretix.eu" target="_blank" rel="noopener">{}</a>'.format(
            pgettext('widget', 'event ticketing powered by pretix')
        )

    def response(self, data):
        self.post_process(data)
        resp = JsonResponse(data)
        resp['Access-Control-Allow-Origin'] = '*'
        return resp

    def get(self, request, *args, **kwargs):
        if not hasattr(request, 'event'):
            return self._get_event_list(request, **kwargs)

        if not request.event.live:
            return self.response({
                'error': ugettext('This ticket shop is currently disabled.')
            })

        self.subevent = None
        if request.event.has_subevents:
            if 'subevent' in kwargs:
                self.subevent = request.event.subevents.filter(pk=kwargs['subevent'], active=True).first()
                if not self.subevent:
                    return self.response({
                        'error': ugettext('The selected date does not exist in this event series.')
                    })
            else:
                return self._get_event_list(request, **kwargs)
        else:
            if 'subevent' in kwargs:
                return self.response({
                    'error': ugettext('This is not an event series.')
                })
        return self._get_event_view(request, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        if 'lang' in request.GET and request.GET.get('lang') in [lc for lc, ll in settings.LANGUAGES]:
            with language(request.GET.get('lang')):
                return self.get(request, **kwargs)
        else:
            return self.get(request, **kwargs)

    def _get_availability(self, ev, event):
        availability = {}
        if ev.presale_is_running and event.settings.event_list_availability and ev.best_availability_state is not None:
            if ev.best_availability_state == Quota.AVAILABILITY_OK:
                availability['color'] = 'green'
                availability['text'] = ugettext('Book now')
            elif event.settings.waiting_list_enabled and ev.best_availability_state >= 0:
                availability['color'] = 'orange'
                availability['text'] = ugettext('Waiting list')
            elif ev.best_availability_state == Quota.AVAILABILITY_RESERVED:
                availability['color'] = 'orange'
                availability['text'] = ugettext('Reserved')
            elif ev.best_availability_state < Quota.AVAILABILITY_RESERVED:
                availability['color'] = 'red'
                availability['text'] = ugettext('Sold out')
        elif ev.presale_is_running:
            availability['color'] = 'green'
            availability['text'] = ugettext('Book now')
        elif ev.presale_has_ended:
            availability['color'] = 'red'
            availability['text'] = ugettext('Sale over')
        elif event.settings.presale_start_show_date and ev.presale_start:
            availability['color'] = 'orange'
            availability['text'] = ugettext('from %(start_date)s') % {'start_date': date_format(ev.presale_start, "SHORT_DATE_FORMAT")}
        else:
            availability['color'] = 'orange'
            availability['text'] = ugettext('Sale soon')
        return availability

    def _serialize_events(self, ebd):
        events = []
        for e in ebd:
            ev = e['event']
            if isinstance(ev, SubEvent):
                event = ev.event
            else:
                event = ev
            tz = pytz.timezone(e['timezone'])
            events.append({
                'name': str(ev.name),
                'time': date_format(ev.date_from.astimezone(tz), 'TIME_FORMAT') if e.get('time') and event.settings.show_times else
                None,
                'continued': e['continued'],
                'location': str(ev.location),
                'date_range': ev.get_date_range_display() + (
                    " " + date_format(ev.date_from.astimezone(tz), "TIME_FORMAT") if event.settings.show_times else ""
                ),
                'availability': self._get_availability(ev, event),
                'event_url': build_absolute_uri(event, 'presale:event.index'),
                'subevent': ev.pk if isinstance(ev, SubEvent) else None,
            })
        return events

    def _get_event_list(self, request, **kwargs):
        data = {}
        o = getattr(request, 'event', request.organizer)
        list_type = self.request.GET.get("style", o.settings.event_list_type)
        data['list_type'] = list_type

        cache_key = ':'.join([
            'widget.py',
            'eventlist',
            request.organizer.slug,
            request.event.slug if hasattr(request, 'event') else '-',
            list_type,
            request.GET.get("year") or "-",
            request.GET.get("month") or "-",
            request.GET.get("old") or "-",
            get_language(),
        ])
        cached_data = cache.get(cache_key)
        if cached_data:
            return self.response(cached_data)

        if list_type == "calendar":
            self._set_month_year()
            _, ndays = calendar.monthrange(self.year, self.month)

            data['date'] = date(self.year, self.month, 1)
            if hasattr(self.request, 'event'):
                tz = pytz.timezone(self.request.event.settings.timezone)
            else:
                tz = pytz.UTC
            before = datetime(self.year, self.month, 1, 0, 0, 0, tzinfo=tz) - timedelta(days=1)
            after = datetime(self.year, self.month, ndays, 0, 0, 0, tzinfo=tz) + timedelta(days=1)

            ebd = defaultdict(list)

            if hasattr(self.request, 'event'):
                add_subevents_for_days(
                    filter_qs_by_attr(self.request.event.subevents_annotated('web'), self.request),
                    before, after, ebd, set(), self.request.event,
                    kwargs.get('cart_namespace')
                )
            else:
                timezones = set()
                add_events_for_days(
                    self.request,
                    filter_qs_by_attr(Event.annotated(self.request.organizer.events, 'web'), self.request),
                    before, after, ebd, timezones
                )
                add_subevents_for_days(filter_qs_by_attr(SubEvent.annotated(SubEvent.objects.filter(
                    event__organizer=self.request.organizer,
                    event__is_public=True,
                    event__live=True,
                ).prefetch_related(
                    'event___settings_objects', 'event__organizer___settings_objects'
                )), self.request), before, after, ebd, timezones)

            data['weeks'] = weeks_for_template(ebd, self.year, self.month)
            for w in data['weeks']:
                for d in w:
                    if not d:
                        continue
                    d['events'] = self._serialize_events(d['events'] or [])
        else:
            if hasattr(self.request, 'event'):
                evs = self.request.event.subevents_sorted(
                    filter_qs_by_attr(self.request.event.subevents_annotated(self.request.sales_channel.identifier), self.request)
                )
                tz = pytz.timezone(request.event.settings.timezone)
                data['events'] = [
                    {
                        'name': str(ev.name),
                        'location': str(ev.location),
                        'date_range': ev.get_date_range_display(tz) + (
                            (" " + ev.get_time_from_display(tz)) if ev.event.settings.show_times else ""
                        ),
                        'availability': self._get_availability(ev, ev.event),
                        'event_url': build_absolute_uri(ev.event, 'presale:event.index'),
                        'subevent': ev.pk,
                    } for ev in evs
                ]
            else:
                data['events'] = []
                qs = self._get_event_queryset()
                for event in qs:
                    tz = pytz.timezone(event.cache.get_or_set('timezone', lambda: event.settings.timezone))
                    if event.has_subevents:
                        dr = daterange(
                            event.min_from.astimezone(tz),
                            (event.max_fromto or event.max_to or event.max_from).astimezone(tz)
                        )
                        avail = {'color': 'none', 'text': ugettext('Event series')}
                    else:
                        dr = event.get_date_range_display(tz) + (
                            " " + event.get_time_from_display(tz) if event.settings.show_times else ""
                        )
                        avail = self._get_availability(event, event)
                    data['events'].append({
                        'name': str(event.name),
                        'location': str(event.location),
                        'date_range': dr,
                        'availability': avail,
                        'event_url': build_absolute_uri(event, 'presale:event.index'),
                    })

        cache.set(cache_key, data, 30)
        # These pages are cached for a really short duration – this should make them pretty accurate, while still
        # providing some protection against burst traffic.
        return self.response(data)

    def _get_event_view(self, request, **kwargs):
        cache_key = ':'.join([
            'widget.py',
            'event',
            request.organizer.slug,
            request.event.slug,
            str(self.subevent.pk) if self.subevent else "",
            request.GET.get("voucher") or "-",
            get_language(),
        ])
        if "cart_id" not in request.GET:
            cached_data = cache.get(cache_key)
            if cached_data:
                return self.response(cached_data)

        data = {
            'currency': request.event.currency,
            'display_net_prices': request.event.settings.display_net_prices,
            'show_variations_expanded': request.event.settings.show_variations_expanded,
            'waiting_list_enabled': request.event.settings.waiting_list_enabled,
            'voucher_explanation_text': str(request.event.settings.voucher_explanation_text),
            'error': None,
            'cart_exists': False
        }

        if 'cart_id' in request.GET and CartPosition.objects.filter(event=request.event, cart_id=request.GET.get('cart_id')).exists():
            data['cart_exists'] = True

        ev = self.subevent or request.event
        data['name'] = str(ev.name)
        fail = False

        if not ev.presale_is_running:
            if ev.presale_has_ended:
                if request.event.settings.presale_has_ended_text:
                    data['error'] = str(request.event.settings.presale_has_ended_text)
                else:
                    data['error'] = ugettext('The presale period for this event is over.')
            elif request.event.settings.presale_start_show_date:
                data['error'] = ugettext('The presale for this event will start on %(date)s at %(time)s.') % {
                    'date': date_format(ev.presale_start.astimezone(request.event.timezone), "SHORT_DATE_FORMAT"),
                    'time': date_format(ev.presale_start.astimezone(request.event.timezone), "TIME_FORMAT"),
                }
            else:
                data['error'] = ugettext('The presale for this event has not yet started.')

        self.voucher = None
        if 'voucher' in request.GET:
            try:
                self.voucher = request.event.vouchers.get(code__iexact=request.GET.get('voucher').strip())
                if self.voucher.redeemed >= self.voucher.max_usages:
                    data['error'] = error_messages['voucher_redeemed']
                    fail = True
                if self.voucher.valid_until is not None and self.voucher.valid_until < now():
                    data['error'] = error_messages['voucher_expired']
                    fail = True

                cart_id = get_or_create_cart_id(request, create=False)
                if cart_id:
                    redeemed_in_carts = CartPosition.objects.filter(
                        Q(voucher=self.voucher) & Q(event=request.event) &
                        (Q(expires__gte=now()) | Q(cart_id=get_or_create_cart_id(request)))
                    )
                else:
                    redeemed_in_carts = CartPosition.objects.filter(
                        Q(voucher=self.voucher) & Q(event=request.event) & Q(expires__gte=now())
                    )
                v_avail = self.voucher.max_usages - self.voucher.redeemed - redeemed_in_carts.count()

                if v_avail < 1:
                    data['error'] = error_messages['voucher_redeemed']
                    fail = True
            except Voucher.DoesNotExist:
                data['error'] = error_messages['voucher_invalid']
                fail = True

        if not fail and (ev.presale_is_running or request.event.settings.show_items_outside_presale_period):
            data['items_by_category'], data['display_add_to_cart'], data['itemnum'] = self._get_items()
            data['display_add_to_cart'] = data['display_add_to_cart'] and ev.presale_is_running
        else:
            data['items_by_category'] = []
            data['display_add_to_cart'] = False
            data['itemnum'] = 0

        data['has_seating_plan'] = ev.seating_plan is not None

        vouchers_exist = self.request.event.get_cache().get('vouchers_exist')
        if vouchers_exist is None:
            vouchers_exist = self.request.event.vouchers.exists()
            self.request.event.get_cache().set('vouchers_exist', vouchers_exist)
        data['vouchers_exist'] = vouchers_exist

        if "cart_id" not in request.GET:
            cache.set(cache_key, data, 10)
            # These pages are cached for a really short duration – this should make them pretty accurate with
            # regards to availability display, while still providing some protection against burst traffic.
        return self.response(data)
