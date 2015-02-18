import datetime
from django.test import TestCase, Client

from pretix.base.models import Item, Organizer, Event, ItemCategory, Quota, Property, PropertyValue, ItemVariation
from pretix.base.tests import BrowserTest, on_platforms


@on_platforms()
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


@on_platforms()
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
