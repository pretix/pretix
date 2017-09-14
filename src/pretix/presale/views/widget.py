from urllib.parse import urljoin

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import Http404, HttpResponse, JsonResponse
from django.utils.formats import date_format
from django.views import View
from easy_thumbnails.files import get_thumbnailer

from pretix.base.i18n import language
from pretix.base.templatetags.rich_text import rich_text
from pretix.presale.views.event import (
    get_grouped_items, item_group_by_category,
)


def widget_js(request, **kwargs):
    resp = HttpResponse(content_type='text/javascript')
    # Provide isolation
    resp.write('(function (siteglobals) {\n')
    resp.write('var module = {}, exports = {};\n')

    files = [
        'vuejs/vue.js' if settings.DEBUG else 'vuejs/vuejs.min.js',
        'pretixpresale/js/widget/docready.js',
        'pretixpresale/js/widget/widget.js',
    ]
    for fname in files:
        f = finders.find(fname)
        with open(f, 'r') as fp:
            resp.write(fp.read())

    if settings.DEBUG:
        resp.write('})(this);\n')
    else:
        # Do not expose debugging variables
        resp.write('})({});\n')

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
        items, display_add_to_cart = get_grouped_items(self.request.event, subevent=self.subevent)
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
            'error': None
        }
        ev = self.subevent or request.event

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

        if ev.presale_is_running or request.event.settings.show_items_outside_presale_period:
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
