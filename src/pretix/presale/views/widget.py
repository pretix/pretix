from urllib.parse import urljoin

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse, JsonResponse
from django.views import View
from easy_thumbnails.files import get_thumbnailer

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


class WidgetAPIProductList(View):
    def get(self, request, **kwargs):
        data = {
            'currency': request.event.currency,
            'display_net_prices': request.event.settings.display_net_prices,
            'show_variations_expanded': request.event.settings.show_variations_expanded,
        }

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

        items, display_add_to_cart = get_grouped_items(self.request.event)
        grps = []
        for cat, g in item_group_by_category(items):

            grps.append({
                'id': cat.pk if cat else None,
                'name': str(cat.name) if cat else None,
                'description': str(rich_text(cat.description)) if cat and cat.description else None,
                'items': [
                    {
                        'id': item.pk,
                        'name': str(item.name),
                        'picture': get_picture(item.picture) if item.picture else None,
                        'description': str(rich_text(item.description)) if item.description else None,
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
                            item.cached_availability[1] if request.event.settings.show_quota_left else None
                        ] if not item.has_variations else None,
                        'variations': [
                            {
                                'id': var.id,
                                'value': str(var.value),
                                'order_max': var.order_max,
                                'description': str(rich_text(var.description)) if var.description else None,
                                'price': price_dict(var.display_price),
                                'avail': [
                                    var.cached_availability[0],
                                    var.cached_availability[1] if request.event.settings.show_quota_left else None
                                ],
                            } for var in item.available_variations
                        ]

                    } for item in g
                ]
            })

        data['items_by_category'] = grps
        data['display_add_to_cart'] = display_add_to_cart

        vouchers_exist = self.request.event.get_cache().get('vouchers_exist')
        if vouchers_exist is None:
            vouchers_exist = self.request.event.vouchers.exists()
            self.request.event.get_cache().set('vouchers_exist', vouchers_exist)
        data['vouchers_exist'] = vouchers_exist

        resp = JsonResponse(data)
        resp['Access-Control-Allow-Origin'] = '*'
        return resp
