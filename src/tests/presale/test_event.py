import datetime
import time

from django.test import TestCase
from django.utils.timezone import now
from tests.base import BrowserTest

from pretix.base.models import (
    Event, Item, ItemCategory, ItemVariation, Organizer, Property,
    PropertyValue, Quota, User,
)


class EventTestMixin:

    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )


class EventMiddlewareTest(EventTestMixin, BrowserTest):

    def setUp(self):
        super().setUp()
        self.driver.implicitly_wait(10)

    def test_event_header(self):
        self.driver.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        self.assertIn(str(self.event.name), self.driver.find_element_by_css_selector("h1").text)

    def test_not_found(self):
        resp = self.client.get('%s/%s/%s/' % (self.live_server_url, 'foo', 'bar'))
        self.assertEqual(resp.status_code, 404)


class ItemDisplayTest(EventTestMixin, BrowserTest):

    def setUp(self):
        super().setUp()
        self.driver.implicitly_wait(10)

    def test_not_active(self):
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=False)
        q.items.add(item)
        self.driver.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", self.driver.find_element_by_css_selector("body").text)

    def test_without_category(self):
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True)
        q.items.add(item)
        self.driver.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", self.driver.find_element_by_css_selector("section .product-row:first-child").text)

    def test_simple_with_category(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
        q.items.add(item)
        self.driver.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        self.assertIn("Entry tickets", self.driver.find_element_by_css_selector("section:nth-of-type(1) h3").text)
        self.assertIn("Early-bird",
                      self.driver.find_element_by_css_selector("section:nth-of-type(1) div:nth-of-type(1)").text)

    def test_simple_without_quota(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
        resp = self.client.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", resp.rendered_content)

    def test_no_variations_in_quota(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
        prop1 = Property.objects.create(event=self.event, name="Color")
        item.properties.add(prop1)
        PropertyValue.objects.create(prop=prop1, value="Red")
        PropertyValue.objects.create(prop=prop1, value="Black")
        q.items.add(item)
        self.driver.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        resp = self.client.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", resp.rendered_content)

    def test_one_variation_in_quota(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
        prop1 = Property.objects.create(event=self.event, name="Color")
        item.properties.add(prop1)
        val1 = PropertyValue.objects.create(prop=prop1, value="Red")
        PropertyValue.objects.create(prop=prop1, value="Black")
        q.items.add(item)
        var1 = ItemVariation.objects.create(item=item)
        var1.values.add(val1)
        q.variations.add(var1)
        self.driver.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        self.assertIn("Early-bird",
                      self.driver.find_element_by_css_selector("section:nth-of-type(1) div:nth-of-type(1)").text)
        for el in self.driver.find_elements_by_link_text('Show variants'):
            self.scroll_and_click(el)
        time.sleep(2)
        self.assertIn("Red",
                      self.driver.find_element_by_css_selector("section:nth-of-type(1)").text)
        self.assertNotIn("Black",
                         self.driver.find_element_by_css_selector("section:nth-of-type(1)").text)

    def test_variation_prices_in_quota(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=12)
        prop1 = Property.objects.create(event=self.event, name="Color")
        item.properties.add(prop1)
        val1 = PropertyValue.objects.create(prop=prop1, value="Red", position=0)
        val2 = PropertyValue.objects.create(prop=prop1, value="Black", position=1)
        q.items.add(item)
        var1 = ItemVariation.objects.create(item=item, default_price=14)
        var1.values.add(val1)
        var2 = ItemVariation.objects.create(item=item)
        var2.values.add(val2)
        q.variations.add(var1)
        q.variations.add(var2)
        self.driver.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        self.assertIn("Early-bird",
                      self.driver.find_element_by_css_selector("section:nth-of-type(1) div:nth-of-type(1)").text)
        for el in self.driver.find_elements_by_link_text('Show variants'):
            self.scroll_and_click(el)
        time.sleep(2)
        self.assertIn("Red",
                      self.driver.find_elements_by_css_selector("section:nth-of-type(1) div.variation")[0].text)
        self.assertIn("14.00",
                      self.driver.find_elements_by_css_selector("section:nth-of-type(1) div.variation")[0].text)
        self.assertIn("Black",
                      self.driver.find_elements_by_css_selector("section:nth-of-type(1) div.variation")[1].text)
        self.assertIn("12.00",
                      self.driver.find_elements_by_css_selector("section:nth-of-type(1) div.variation")[1].text)


class LoginTest(EventTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('demo@demo.dummy', 'demo')

    def test_login_invalid(self):
        response = self.client.post(
            '/%s/%s/login' % (self.orga.slug, self.event.slug),
            {
                'form': 'login',
                'email': 'demo@demo.foo',
                'password': 'bar'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('alert-danger', response.rendered_content)

    def test_login_valid(self):
        response = self.client.post(
            '/%s/%s/login' % (self.orga.slug, self.event.slug),
            {
                'form': 'login',
                'email': 'demo@demo.dummy',
                'password': 'demo'
            }
        )
        self.assertEqual(response.status_code, 302)

    def test_login_already_logged_in(self):
        self.assertTrue(self.client.login(email='demo@demo.dummy', password='demo'))
        response = self.client.get(
            '/%s/%s/login' % (self.orga.slug, self.event.slug),
        )
        self.assertEqual(response.status_code, 302)

    def test_logout(self):
        self.assertTrue(self.client.login(email='demo@demo.dummy', password='demo'))
        response = self.client.get(
            '/%s/%s/logout' % (self.orga.slug, self.event.slug),
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get(
            '/%s/%s/login' % (self.orga.slug, self.event.slug),
        )
        self.assertEqual(response.status_code, 200)


class DeadlineTest(EventTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('demo@demo.dummy', 'demo')

    def test_not_yet_started(self):
        self.assertTrue(self.client.login(email='demo@demo.dummy', password='demo'))
        self.event.presale_start = now() + datetime.timedelta(days=1)
        self.event.save()
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('alert-info', response.rendered_content)
        self.assertNotIn('checkout-button-row', response.rendered_content)
        response = self.client.post(
            '/%s/%s/cart/add' % (self.orga.slug, self.event.slug),
            follow=True
        )
        self.assertIn('alert-danger', response.rendered_content)
        self.assertIn('not yet started', response.rendered_content)

    def test_over(self):
        self.assertTrue(self.client.login(email='demo@demo.dummy', password='demo'))
        self.event.presale_end = now() - datetime.timedelta(days=1)
        self.event.save()
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('alert-info', response.rendered_content)
        self.assertNotIn('checkout-button-row', response.rendered_content)
        response = self.client.post(
            '/%s/%s/cart/add' % (self.orga.slug, self.event.slug),
            follow=True
        )
        self.assertIn('alert-danger', response.rendered_content)
        self.assertIn('is over', response.rendered_content)

    def test_not_set(self):
        self.event.presale_start = None
        self.event.presale_end = None
        self.event.save()
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('alert-info', response.rendered_content)
        self.assertIn('checkout-button-row', response.rendered_content)
        response = self.client.post(
            '/%s/%s/cart/add' % (self.orga.slug, self.event.slug)
        )
        self.assertNotEqual(response.status_code, 403)

    def test_in_time(self):
        self.event.presale_start = now() - datetime.timedelta(days=1)
        self.event.presale_end = now() + datetime.timedelta(days=1)
        self.event.save()
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('alert-info', response.rendered_content)
        self.assertIn('checkout-button-row', response.rendered_content)
        response = self.client.post(
            '/%s/%s/cart/add' % (self.orga.slug, self.event.slug)
        )
        self.assertNotEqual(response.status_code, 403)
