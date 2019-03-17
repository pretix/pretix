import datetime
import json
from decimal import Decimal

from bs4 import BeautifulSoup
from django.conf import settings
from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import Order, OrderPosition
from pretix.presale.style import regenerate_css, regenerate_organizer_css

from .test_cart import CartTestMixin


class WidgetCartTest(CartTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.order = Order.objects.create(
            status=Order.STATUS_PENDING,
            event=self.event,
            email='admin@localhost',
            datetime=now() - datetime.timedelta(days=3),
            expires=now() + datetime.timedelta(days=11),
            total=Decimal("23"),
            locale='en'
        )
        self.ticket_pos = OrderPosition.objects.create(
            order=self.order,
            item=self.ticket,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={'full_name': "Peter"}
        )

    def test_iframe_entry_view_wrapper(self):
        self.client.get('/%s/%s/?iframe=1&locale=de' % (self.orga.slug, self.event.slug))
        assert 'iframe_session' in self.client.session
        assert self.client.cookies[settings.LANGUAGE_COOKIE_NAME].value == "de"

    def test_allow_frame_if_namespaced(self):
        response = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        assert 'X-Frame-Options' in response
        response = self.client.get('/%s/%s/w/aaaaaaaaaaaaaaaa/' % (self.orga.slug, self.event.slug))
        assert 'X-Frame-Options' not in response

        response = self.client.get('/%s/%s/waitinglist' % (self.orga.slug, self.event.slug))
        assert 'X-Frame-Options' in response
        response = self.client.get('/%s/%s/w/aaaaaaaaaaaaaaaa/waitinglist' % (self.orga.slug, self.event.slug))
        assert 'X-Frame-Options' not in response

    def test_allow_frame_on_order(self):
        response = self.client.get('/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                            self.order.secret))
        assert 'X-Frame-Options' not in response
        response = self.client.get('/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code,
                                                                  self.order.secret))
        assert 'X-Frame-Options' not in response
        response = self.client.get('/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code,
                                                                      self.order.secret))
        assert 'X-Frame-Options' not in response
        response = self.client.get('/%s/%s/order/%s/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code,
                                                                  self.order.secret))
        assert 'X-Frame-Options' not in response

    def test_allow_cors_if_namespaced(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'ajax': 1
        })
        assert 'Access-Control-Allow-Origin' not in response
        response = self.client.post('/%s/%s/w/aaaaaaaaaaaaaaaa/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'ajax': 1
        })
        assert response['Access-Control-Allow-Origin'] == '*'

    def test_cart_isolation(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert len(doc.select('.cart .cart-row')) == 2
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)

        response = self.client.get('/%s/%s/w/aaaaaaaaaaaaaaaa/' % (self.orga.slug, self.event.slug))
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert len(doc.select('.cart .cart-row')) == 0
        response = self.client.post('/%s/%s/w/aaaaaaaaaaaaaaaa/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/w/aaaaaaaaaaaaaaaa/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert len(doc.select('.cart .cart-row')) == 2
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)

        response = self.client.get('/%s/%s/w/aaaaaaaaaaaaaaab/' % (self.orga.slug, self.event.slug))
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert len(doc.select('.cart .cart-row')) == 0
        response = self.client.post('/%s/%s/w/aaaaaaaaaaaaaaab/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/w/aaaaaaaaaaaaaaab/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert len(doc.select('.cart .cart-row')) == 2
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)

    def test_product_list_view(self):
        response = self.client.get('/%s/%s/widget/product_list' % (self.orga.slug, self.event.slug))
        assert response['Access-Control-Allow-Origin'] == '*'
        data = json.loads(response.content.decode())
        assert data == {
            "currency": "EUR",
            "show_variations_expanded": False,
            "display_net_prices": False,
            "vouchers_exist": False,
            "waiting_list_enabled": False,
            "error": None,
            "items_by_category": [
                {
                    "items": [
                        {
                            "require_voucher": False,
                            "order_min": None,
                            "max_price": None,
                            "price": {"gross": "23.00", "net": "19.33", "tax": "3.67", "name": "", "rate": "19.00", "includes_mixed_tax_rate": False},
                            "picture": None,
                            "has_variations": 0,
                            "description": None,
                            "min_price": None,
                            "avail": [100, None],
                            "variations": [],
                            "id": self.ticket.pk,
                            "free_price": False,
                            "original_price": None,
                            "name": "Early-bird ticket",
                            "order_max": 4
                        },
                        {
                            "require_voucher": False,
                            "order_min": None,
                            "max_price": "14.00",
                            "price": None,
                            "picture": None,
                            "has_variations": 4,
                            "description": None,
                            "min_price": "12.00",
                            "avail": None,
                            "variations": [
                                {
                                    "value": "Red",
                                    "id": self.shirt_red.pk,
                                    "price": {"gross": "14.00", "net": "11.76", "tax": "2.24", "name": "",
                                              "rate": "19.00", "includes_mixed_tax_rate": False},
                                    "description": None,
                                    "avail": [100, None],
                                    "order_max": 2
                                },
                                {
                                    "value": "Blue",
                                    "id": self.shirt_blue.pk,
                                    "price": {"gross": "12.00", "net": "10.08", "tax": "1.92", "name": "",
                                              "rate": "19.00", "includes_mixed_tax_rate": False},
                                    "description": None,
                                    "avail": [100, None],
                                    "order_max": 2
                                }
                            ],
                            "id": self.shirt.pk,
                            "free_price": False,
                            "original_price": None,
                            "name": "T-Shirt",
                            "order_max": None
                        }
                    ],
                    "description": None,
                    "id": self.category.pk,
                    "name": "Everything"
                }
            ],
            "itemnum": 2,
            "display_add_to_cart": True,
            "cart_exists": False
        }

    def test_product_list_view_with_voucher(self):
        self.event.vouchers.create(item=self.ticket, code="ABCDE")
        response = self.client.get('/%s/%s/widget/product_list?voucher=ABCDE' % (self.orga.slug, self.event.slug))
        assert response['Access-Control-Allow-Origin'] == '*'
        data = json.loads(response.content.decode())
        assert data == {
            "currency": "EUR",
            "show_variations_expanded": False,
            "display_net_prices": False,
            "vouchers_exist": True,
            "waiting_list_enabled": False,
            "error": None,
            "items_by_category": [
                {
                    "items": [
                        {
                            "require_voucher": False,
                            "order_min": None,
                            "max_price": None,
                            "price": {"gross": "23.00", "net": "19.33", "tax": "3.67", "name": "", "rate": "19.00", "includes_mixed_tax_rate": False},
                            "picture": None,
                            "has_variations": 0,
                            "description": None,
                            "min_price": None,
                            "avail": [100, None],
                            "variations": [],
                            "id": self.ticket.pk,
                            "free_price": False,
                            "original_price": None,
                            "name": "Early-bird ticket",
                            "order_max": 4
                        },
                    ],
                    "description": None,
                    "id": self.category.pk,
                    "name": "Everything"
                }
            ],
            "itemnum": 1,
            "display_add_to_cart": True,
            "cart_exists": False
        }

    def test_product_list_view_with_voucher_expired(self):
        self.event.vouchers.create(item=self.ticket, code="ABCDE", valid_until=now() - datetime.timedelta(days=1))
        response = self.client.get('/%s/%s/widget/product_list?voucher=ABCDE' % (self.orga.slug, self.event.slug))
        assert response['Access-Control-Allow-Origin'] == '*'
        data = json.loads(response.content.decode())
        assert data == {
            "currency": "EUR",
            "show_variations_expanded": False,
            "display_net_prices": False,
            "vouchers_exist": True,
            "waiting_list_enabled": False,
            "error": "This voucher is expired.",
            "items_by_category": [],
            "display_add_to_cart": False,
            "cart_exists": False,
            "itemnum": 0,
        }

    def test_css_customized(self):
        response = self.client.get('/%s/%s/widget/v1.css' % (self.orga.slug, self.event.slug))
        c = b"".join(response.streaming_content).decode()
        assert '#7f5a91' in c
        assert '#33c33c' not in c
        assert '#34c34c' not in c

        self.orga.settings.primary_color = "#33c33c"
        regenerate_organizer_css.apply(args=(self.orga.pk,))
        response = self.client.get('/%s/%s/widget/v1.css' % (self.orga.slug, self.event.slug))
        c = b"".join(response.streaming_content).decode()
        assert '#7f5a91' not in c
        assert '#33c33c' in c
        assert '#34c34c' not in c

        self.event.settings.primary_color = "#34c34c"
        regenerate_css.apply(args=(self.event.pk,))
        response = self.client.get('/%s/%s/widget/v1.css' % (self.orga.slug, self.event.slug))
        c = b"".join(response.streaming_content).decode()
        assert '#7f5a91' not in c
        assert '#33c33c' not in c
        assert '#34c34c' in c

    def test_js_localized(self):
        response = self.client.get('/widget/v1.en.js')
        c = response.content.decode()
        assert '%m/%d/%Y' in c
        assert '%d.%m.%Y' not in c
        response = self.client.get('/widget/v1.de.js')
        c = response.content.decode()
        assert '%m/%d/%Y' not in c
        assert '%d.%m.%Y' in c

    def test_product_list_view_with_bundle_sold_out(self):
        self.quota_shirts.size = 0
        self.quota_shirts.save()
        self.ticket.bundles.create(bundled_item=self.shirt, bundled_variation=self.shirt_blue,
                                   designated_price=2, count=1)
        response = self.client.get('/%s/%s/widget/product_list' % (self.orga.slug, self.event.slug))
        assert response['Access-Control-Allow-Origin'] == '*'
        data = json.loads(response.content.decode())
        assert data["items_by_category"][0]["items"][0]["avail"] == [0, None]

    def test_product_list_view_with_bundle_mixed_tax_rate(self):
        self.tr7 = self.event.tax_rules.create(rate=Decimal('7.00'))
        self.shirt.tax_rule = self.tr7
        self.shirt.save()
        self.ticket.bundles.create(bundled_item=self.shirt, bundled_variation=self.shirt_blue,
                                   designated_price=2, count=1)
        response = self.client.get('/%s/%s/widget/product_list' % (self.orga.slug, self.event.slug))
        assert response['Access-Control-Allow-Origin'] == '*'
        data = json.loads(response.content.decode())
        assert data["items_by_category"][0]["items"][0]["price"] == {
            "gross": "23.00",
            "net": "19.33",
            "tax": "3.67",
            "name": "",
            "rate": "19.00",
            "includes_mixed_tax_rate": True
        }
