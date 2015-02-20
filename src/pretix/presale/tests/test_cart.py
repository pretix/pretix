import datetime
import time
from bs4 import BeautifulSoup
from django.test import TestCase

from pretix.base.models import Item, Organizer, Event, ItemCategory, Quota, Property, PropertyValue, ItemVariation, User
from pretix.base.tests import BrowserTest


class CartTestMixin:

    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            )
        self.user = User.objects.create_local_user(self.event, 'demo', 'demo')
        self.category = ItemCategory.objects.create(event=self.event, name="Everything", position=0)
        self.quota_shirts = Quota.objects.create(event=self.event, name='Shirts', size=2)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', category=self.category, default_price=12)
        prop1 = Property.objects.create(event=self.event, name="Color")
        self.shirt.properties.add(prop1)
        val1 = PropertyValue.objects.create(prop=prop1, value="Red", position=0)
        val2 = PropertyValue.objects.create(prop=prop1, value="Black", position=1)
        self.quota_shirts.items.add(self.shirt)
        self.shirt_red = ItemVariation.objects.create(item=self.shirt, default_price=14)
        self.shirt_red.values.add(val1)
        var2 = ItemVariation.objects.create(item=self.shirt)
        var2.values.add(val2)
        self.quota_shirts.variations.add(self.shirt_red)
        self.quota_shirts.variations.add(var2)
        self.quota_tickets = Quota.objects.create(event=self.event, name='Tickets', size=5)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          category=self.category, default_price=23)
        self.quota_tickets.items.add(self.ticket)


class CartBrowserTest(CartTestMixin, BrowserTest):

    def test_not_logged_in(self):
        self.driver.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        # add the entry ticket to cart
        self.driver.find_element_by_css_selector('input[type=number][name=item_%s]' % self.ticket.identity).send_keys('1')
        self.scroll_and_click(self.driver.find_element_by_css_selector('.checkout-button-row button'))
        # should redirect to login page
        self.driver.find_element_by_name('username')

    def test_simple_login(self):
        self.driver.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        # add the entry ticket to cart
        self.driver.find_element_by_css_selector('input[type=number][name=item_%s]' % self.ticket.identity).send_keys('1')
        self.scroll_and_click(self.driver.find_element_by_css_selector('.checkout-button-row button'))
        # should redirect to login page
        # open the login accordion
        self.scroll_and_click(self.driver.find_element_by_css_selector('a[href*=loginForm]'))
        time.sleep(1)
        # enter login details
        self.driver.find_element_by_css_selector('#loginForm input[name=username]').send_keys('demo')
        self.driver.find_element_by_css_selector('#loginForm input[name=password]').send_keys('demo')
        self.scroll_and_click(self.driver.find_element_by_css_selector('#loginForm button.btn-primary'))
        # should display our ticket
        self.assertIn('Early-bird', self.driver.find_element_by_css_selector('.cart-row:first-child').text)


class CartTest(CartTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.assertTrue(self.client.login(username='demo@%s.event.pretix' % self.event.identity, password='demo'))

    def test_simple(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)

    def test_variation(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_' + self.shirt.identity + '_' + self.shirt_red.identity: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('Shirt', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('Red', doc.select('.cart .cart-row')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('14', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('14', doc.select('.cart .cart-row')[0].select('.price')[1].text)

    def test_count(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '2'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('2', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('46', doc.select('.cart .cart-row')[0].select('.price')[1].text)
