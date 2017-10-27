from django.conf import settings
from django.test import TestCase

from .test_cart import CartTestMixin


class WidgetCartTest(CartTestMixin, TestCase):
    def test_iframe_entry_view_wrapper(self):
        self.client.get('/%s/%s/?iframe=1&locale=de' % (self.orga.slug, self.event.slug))
        assert 'iframe_session' in self.client.session
        assert self.client.cookies[settings.LANGUAGE_COOKIE_NAME].value == "de"

    def test_allow_frame_if_namespaced(self):
        response = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        assert 'X-Frame-Options' in response
        response = self.client.get('/%s/%s/w/aaaaaaaaaaaaaaaa/' % (self.orga.slug, self.event.slug))
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

        # Test Cart isolation
        # Test product list view
        # Test CSS output
        # Test JS output
