import datetime
from decimal import Decimal
from bs4 import BeautifulSoup
from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import Organizer, Event, Order, User, ItemCategory, Quota, Item, Property, PropertyValue, \
    ItemVariation, OrderPosition


class OrdersTest(TestCase):

    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        self.user = User.objects.create_local_user(self.event, 'demo', 'foo')
        self.assertTrue(self.client.login(username='demo@%s.event.pretix' % self.event.identity, password='foo'))

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

        self.order = Order.objects.create(
            status=Order.STATUS_PENDING,
            event=self.event,
            user=self.user,
            datetime=now() - datetime.timedelta(days=3),
            expires=now() + datetime.timedelta(days=11),
            total=Decimal("23")
        )
        self.ticket_pos = OrderPosition.objects.create(
            order=self.order,
            item=self.ticket,
            variation=None,
            price=Decimal("14"),
            attendee_name="Peter"
        )

    def test_orders_list(self):
        response = self.client.get(
            '/%s/%s/orders' % (self.orga.slug, self.event.slug)
        )
        doc = BeautifulSoup(response.rendered_content)
        rows = doc.select("table tbody tr")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn(self.order.code, row.text)
        self.assertIn(str(self.order.total), row.text)
