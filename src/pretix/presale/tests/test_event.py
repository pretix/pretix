import datetime
import time

from pretix.base.models import Item, Organizer, Event, ItemCategory, Quota, Property, PropertyValue, ItemVariation, User
from pretix.base.tests import BrowserTest


class EventMiddlewareTest(BrowserTest):

    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        self.driver.implicitly_wait(10)

    def test_event_header(self):
        self.driver.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        self.assertIn(self.event.name, self.driver.find_element_by_css_selector("h1").text)

    def test_not_found(self):
        resp = self.client.get('%s/%s/%s/' % (self.live_server_url, 'foo', 'bar'))
        self.assertEqual(resp.status_code, 404)


class ItemDisplayTest(BrowserTest):

    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        self.driver.implicitly_wait(10)

    def test_without_category(self):
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket')
        q.items.add(item)
        self.driver.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", self.driver.find_element_by_css_selector("section .product-row:first-child").text)

    def test_simple_with_category(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c)
        q.items.add(item)
        self.driver.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        self.assertIn("Entry tickets", self.driver.find_element_by_css_selector("section:nth-of-type(1) h3").text)
        self.assertIn("Early-bird",
                      self.driver.find_element_by_css_selector("section:nth-of-type(1) div:nth-of-type(1)").text)

    def test_simple_without_quota(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        Item.objects.create(event=self.event, name='Early-bird ticket', category=c)
        resp = self.client.get('%s/%s/%s/' % (self.live_server_url, self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", resp.rendered_content)

    def test_no_variations_in_quota(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c)
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
        item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c)
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
        self.assertIn("Red",
                      self.driver.find_elements_by_css_selector("section:nth-of-type(1) div.variation")[0].text)
        self.assertIn("14.00",
                      self.driver.find_elements_by_css_selector("section:nth-of-type(1) div.variation")[0].text)
        self.assertIn("Black",
                      self.driver.find_elements_by_css_selector("section:nth-of-type(1) div.variation")[1].text)
        self.assertIn("12.00",
                      self.driver.find_elements_by_css_selector("section:nth-of-type(1) div.variation")[1].text)


class CartTest(BrowserTest):

    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        self.user = User.objects.create_local_user(self.event, 'demo', 'demo')
        self.driver.implicitly_wait(10)
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
        self.quota_tickets = Quota.objects.create(event=self.event, name='Tickets', size=1)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          category=self.category, default_price=23)
        self.quota_tickets.items.add(self.ticket)

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
