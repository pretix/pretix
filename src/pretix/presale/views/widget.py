import hashlib
import json
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.template import Context, Engine
from django.template.loader import get_template
from django.utils.formats import date_format
from django.utils.timezone import now
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.decorators.http import condition
from django.views.i18n import (
    get_formats, get_javascript_catalog, js_catalog_template,
)
from easy_thumbnails.files import get_thumbnailer
from lxml import etree

from pretix.base.i18n import language
from pretix.base.models import CartPosition, Voucher
from pretix.base.services.cart import error_messages
from pretix.base.settings import GlobalSettingsObject
from pretix.base.templatetags.rich_text import rich_text
from pretix.presale.views.cart import get_or_create_cart_id
from pretix.presale.views.event import (
    get_grouped_items, item_group_by_category,
)


def indent(s):
    return s.replace('\n', '\n  ')


def widget_css_etag(request, **kwargs):
    return request.event.settings.presale_widget_css_checksum or request.organizer.settings.presale_widget_css_checksum


def widget_js_etag(request, lang, **kwargs):
    gs = GlobalSettingsObject()
    return gs.settings.get('widget_checksum_{}'.format(lang))


@condition(etag_func=widget_css_etag)
@cache_page(60)
def widget_css(request, **kwargs):
    if request.event.settings.presale_widget_css_file:
        resp = FileResponse(default_storage.open(request.event.settings.presale_widget_css_file),
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

        catalog, plural = get_javascript_catalog(lang, 'djangojs', ['pretix'])
        catalog = dict((k, v) for k, v in catalog.items() if k.startswith('widget\u0004'))
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
            'pretixpresale/js/widget/docready.js',
            'pretixpresale/js/widget/floatformat.js',
            'pretixpresale/js/widget/widget.js',
        ]
        for fname in files:
            f = finders.find(fname)
            with open(f, 'r') as fp:
                code.append(fp.read())

        if settings.DEBUG:
            code.append('})(this);\n')
        else:
            # Do not expose debugging variables
            code.append('})({});\n')
    return ''.join(code)


@condition(etag_func=widget_js_etag)
@cache_page(60)
def widget_js(request, lang, **kwargs):
    if lang not in [lc for lc, ll in settings.LANGUAGES]:
        raise Http404()

    gs = GlobalSettingsObject()
    fname = gs.settings.get('widget_file_{}'.format(lang))
    print(fname, settings.DEBUG)
    if not fname or settings.DEBUG:
        data = generate_widget_js(lang).encode()
        checksum = hashlib.sha1(data).hexdigest()
        if not fname:
            newname = default_storage.save(
                'widget/widget.{}.{}.js'.format(lang, checksum),
                ContentFile(data)
            )
            gs.settings.set('widget_file_{}'.format(lang), 'file://' + newname)
            gs.settings.set('widget_checksum_{}'.format(lang), checksum)
        resp = HttpResponse(data, content_type='text/javascript')
    else:
        resp = FileResponse(default_storage.open(fname), content_type='text/javascript')
    return resp


def price_dict(price):
    return {
        'gross': price.gross,
        'net': price.net,
        'tax': price.tax,
        'rate': price.rate,
        'name': str(price.name)
    }


def get_picture(picture):
    thumb = get_thumbnailer(picture)['productlist']
    return urljoin(settings.SITE_URL, thumb.url)


class WidgetAPIProductList(View):

    def _get_items(self):
        items, display_add_to_cart = get_grouped_items(
            self.request.event, subevent=self.subevent, voucher=self.voucher
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
                        'picture': get_picture(item.picture) if item.picture else None,
                        'description': str(rich_text(item.description, safelinks=False)) if item.description else None,
                        'has_variations': item.has_variations,
                        'require_voucher': item.require_voucher,
                        'order_min': item.min_per_order,
                        'order_max': item.order_max if not item.has_variations else None,
                        'price': price_dict(item.display_price) if not item.has_variations else None,
                        'min_price': item.min_price if item.has_variations else None,
                        'max_price': item.max_price if item.has_variations else None,
                        'free_price': item.free_price,
                        'avail': [
                            item.cached_availability[0],
                            item.cached_availability[1] if self.request.event.settings.show_quota_left else None
                        ] if not item.has_variations else None,
                        'variations': [
                            {
                                'id': var.id,
                                'value': str(var.value),
                                'order_max': var.order_max,
                                'description': str(rich_text(var.description, safelinks=False)) if var.description else None,
                                'price': price_dict(var.display_price),
                                'avail': [
                                    var.cached_availability[0],
                                    var.cached_availability[1] if self.request.event.settings.show_quota_left else None
                                ],
                            } for var in item.available_variations
                        ]

                    } for item in g
                ]
            })
        return grps, display_add_to_cart

    def dispatch(self, request, *args, **kwargs):
        self.subevent = None
        if request.event.has_subevents:
            if 'subevent' in kwargs:
                self.subevent = request.event.subevents.filter(pk=kwargs['subevent'], active=True).first()
                if not self.subevent:
                    raise Http404()
            else:
                raise Http404()
        else:
            if 'subevent' in kwargs:
                raise Http404()

        if 'lang' in request.GET and request.GET.get('lang') in [lc for lc, ll in settings.LANGUAGES]:
            with language(request.GET.get('lang')):
                return super().dispatch(request, *args, **kwargs)
        else:
            return super().dispatch(request, *args, **kwargs)

    def get(self, request, **kwargs):
        data = {
            'currency': request.event.currency,
            'display_net_prices': request.event.settings.display_net_prices,
            'show_variations_expanded': request.event.settings.show_variations_expanded,
            'waiting_list_enabled': request.event.settings.waiting_list_enabled,
            'error': None,
            'cart_exists': False
        }

        if 'cart_id' in request.GET and CartPosition.objects.filter(event=request.event, cart_id=request.GET.get('cart_id')).exists():
            data['cart_exists'] = True

        ev = self.subevent or request.event
        fail = False

        if not ev.presale_is_running:
            if ev.presale_has_ended:
                data['error'] = 'The presale period for this event is over.'
            elif request.event.settings.presale_start_show_date:
                data['error'] = 'The presale for this event will start on %(date)s at %(time)s.' % {
                    'date': date_format(ev.presale_start, "SHORT_DATE_FORMAT"),
                    'time': date_format(ev.presale_start, "TIME_FORMAT"),
                }
            else:
                data['error'] = 'The presale for this event has not yet started.'

        self.voucher = None
        if 'voucher' in request.GET:
            try:
                self.voucher = request.event.vouchers.get(code=request.GET.get('voucher').strip())
                if self.voucher.redeemed >= self.voucher.max_usages:
                    data['error'] = error_messages['voucher_redeemed']
                    fail = True
                if self.voucher.valid_until is not None and self.voucher.valid_until < now():
                    data['error'] = error_messages['voucher_expired']
                    fail = True

                redeemed_in_carts = CartPosition.objects.filter(
                    Q(voucher=self.voucher) & Q(event=request.event) &
                    (Q(expires__gte=now()) | Q(cart_id=get_or_create_cart_id(request)))
                )
                v_avail = self.voucher.max_usages - self.voucher.redeemed - redeemed_in_carts.count()

                if v_avail < 1:
                    data['error'] = error_messages['voucher_redeemed']
                    fail = True
            except Voucher.DoesNotExist:
                data['error'] = error_messages['voucher_invalid']
                fail = True

        if not fail and (ev.presale_is_running or request.event.settings.show_items_outside_presale_period):
            data['items_by_category'], data['display_add_to_cart'] = self._get_items()
            data['display_add_to_cart'] = data['display_add_to_cart'] and ev.presale_is_running
        else:
            data['items_by_category'] = []
            data['display_add_to_cart'] = False

        vouchers_exist = self.request.event.get_cache().get('vouchers_exist')
        if vouchers_exist is None:
            vouchers_exist = self.request.event.vouchers.exists()
            self.request.event.get_cache().set('vouchers_exist', vouchers_exist)
        data['vouchers_exist'] = vouchers_exist

        resp = JsonResponse(data)
        resp['Access-Control-Allow-Origin'] = '*'
        return resp
