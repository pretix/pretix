from decimal import Decimal

from django_scopes import scopes_disabled

from pretix.base.models import OrderPayment

from ..presale.test_orders import BaseOrdersTest


class ReturnURLTest(BaseOrdersTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.event.enable_plugin("pretix.plugins.returnurl")
        self.event.save()
        self.event.settings.returnurl_prefix = 'https://example.com'
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('payment_testdummy__enabled', True)
        self.order.payments.create(
            provider='manual',
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            amount=Decimal('10.00'),
        )

    def test_redirect_once(self):
        r = self.client.get(
            '/%s/%s/order/%s/%s/pay/change?return_url=https://example.com/foo/var/' % (
                self.orga.slug, self.event.slug, self.order.code, self.order.secret
            )
        )
        assert r.status_code == 200
        r = self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'banktransfer'
            },
            follow=False
        )
        assert r['Location'].endswith('/confirm')
        r = self.client.post(
            r['Location'],
            follow=False
        )
        assert r['Location'] == '/%s/%s/order/%s/%s/' % (
            self.orga.slug, self.event.slug, self.order.code, self.order.secret
        )
        r = self.client.get(
            r['Location'],
            follow=False
        )
        assert r['Location'] == 'https://example.com/foo/var/'
        r = self.client.get(
            '/%s/%s/order/%s/%s/' % (
                self.orga.slug, self.event.slug, self.order.code, self.order.secret
            )
        )
        assert r.status_code == 200

    def test_redirect_enforce_prefix_match(self):
        r = self.client.get(
            '/%s/%s/order/%s/%s/pay/change?return_url=https://example.org/foo/var/' % (
                self.orga.slug, self.event.slug, self.order.code, self.order.secret
            )
        )
        assert r.status_code == 403

    def test_redirect_enforce_prefix_set(self):
        del self.event.settings.returnurl_prefix
        r = self.client.get(
            '/%s/%s/order/%s/%s/pay/change?return_url=https://example.org/foo/var/' % (
                self.orga.slug, self.event.slug, self.order.code, self.order.secret
            )
        )
        assert r.status_code == 403
