from datetime import timedelta
from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import (
    Event, Organizer, Item, ItemVariation,
    Property, PropertyValue, User, Quota,
    Order, OrderPosition, CartPosition)
from pretix.base.types import VariationDict


class ItemVariationsTest(TestCase):
    """
    This test case tests various methods around the properties /
    variations concept.
    """
    @classmethod
    def setUpTestData(cls):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        cls.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )
        cls.p_size = Property.objects.create(event=cls.event, name='Size')
        cls.pv_size_s = PropertyValue.objects.create(prop=cls.p_size, value='S')
        cls.pv_size_m = PropertyValue.objects.create(prop=cls.p_size, value='M')
        PropertyValue.objects.create(prop=cls.p_size, value='L')
        cls.p_color = Property.objects.create(event=cls.event, name='Color')
        cls.pv_color_black = PropertyValue.objects.create(prop=cls.p_color, value='black')
        PropertyValue.objects.create(prop=cls.p_color, value='blue')

    def test_variationdict(self):
        i = Item.objects.create(event=self.event, name='Dummy')
        i.properties.add(self.p_size)
        iv = ItemVariation.objects.create(item=i)
        iv.values.add(self.pv_size_s)

        variations = i.get_all_variations()

        for vd in variations:
            for i, v in vd.relevant_items():
                self.assertIs(type(v), PropertyValue)

            for v in vd.relevant_values():
                self.assertIs(type(v), PropertyValue)

            if vd[self.p_size.pk] == self.pv_size_s:
                vd1 = vd

        vd2 = VariationDict()
        vd2[self.p_size.pk] = self.pv_size_s

        self.assertEqual(vd2.identify(), vd1.identify())
        self.assertEqual(vd2, vd1)

        vd2[self.p_size.pk] = self.pv_size_m

        self.assertNotEqual(vd2.identify(), vd.identify())
        self.assertNotEqual(vd2, vd1)

        vd3 = vd2.copy()
        self.assertEqual(vd3, vd2)

        vd2[self.p_size.pk] = self.pv_size_s
        self.assertNotEqual(vd3, vd2)

        vd4 = VariationDict()
        vd4[4] = 'b'
        vd4[2] = 'a'
        self.assertEqual(vd4.ordered_values(), ['a', 'b'])

    def test_get_all_variations(self):
        i = Item.objects.create(event=self.event, name='Dummy')

        # No properties available
        v = i.get_all_variations()
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0], {})

        # One property, no variations
        i.properties.add(self.p_size)
        v = i.get_all_variations()
        self.assertIs(type(v), list)
        self.assertEqual(len(v), 3)
        values = []
        for var in v:
            self.assertIs(type(var), VariationDict)
            self.assertIn(self.p_size.pk, var)
            self.assertIs(type(var[self.p_size.pk]), PropertyValue)
            values.append(var[self.p_size.pk].value)
        self.assertEqual(sorted([str(V) for V in values]), sorted(['S', 'M', 'L']))

        # One property, one variation
        iv = ItemVariation.objects.create(item=i)
        iv.values.add(self.pv_size_s)
        v = i.get_all_variations()
        self.assertIs(type(v), list)
        self.assertEqual(len(v), 3)
        values = []
        num_variations = 0
        for var in v:
            self.assertIs(type(var), VariationDict)
            if 'variation' in var and type(var['variation']) is ItemVariation:
                self.assertEqual(iv.pk, var['variation'].pk)
                values.append(var['variation'].values.all()[0].value)
                num_variations += 1
            elif self.p_size.pk in var:
                self.assertIs(type(var[self.p_size.pk]), PropertyValue)
                values.append(var[self.p_size.pk].value)
        self.assertEqual(sorted([str(V) for V in values]), sorted(['S', 'M', 'L']))
        self.assertEqual(num_variations, 1)

        # Two properties, one variation
        i.properties.add(self.p_color)
        iv.values.add(self.pv_color_black)
        v = i.get_all_variations()
        self.assertIs(type(v), list)
        self.assertEqual(len(v), 6)
        values = []
        num_variations = 0
        for var in v:
            self.assertIs(type(var), VariationDict)
            if 'variation' in var:
                self.assertEqual(iv.pk, var['variation'].pk)
                values.append(sorted([str(ivv.value) for ivv in iv.values.all()]))
                self.assertEqual(sorted([str(ivv.value) for ivv in iv.values.all()]), sorted(['S', 'black']))
                num_variations += 1
            else:
                values.append(sorted([str(pv.value) for pv in var.values()]))
        self.assertEqual(sorted(values), sorted([
            ['S', 'black'],
            ['S', 'blue'],
            ['M', 'black'],
            ['M', 'blue'],
            ['L', 'black'],
            ['L', 'blue'],
        ]))
        self.assertEqual(num_variations, 1)


class VersionableTestCase(TestCase):

    def test_shallow_cone(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )
        old = Item.objects.create(event=event, name='Dummy', default_price=14)
        prop = Property.objects.create(event=event, name='Size')
        old.properties.add(prop)
        new = old.clone_shallow()
        self.assertIsNone(new.version_end_date)
        self.assertIsNotNone(old.version_end_date)
        self.assertEqual(new.properties.count(), 0)
        self.assertEqual(old.properties.count(), 1)


class UserTestCase(TestCase):

    def test_identifier_local(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )
        u = User(event=event, username='tester')
        u.set_password("test")
        u.save()
        self.assertEqual(u.identifier, "%s@%s.event.pretix" % (u.username.lower(), event.id))

    def test_identifier_global(self):
        u = User(email='test@example.com')
        u.set_password("test")
        u.save()
        self.assertEqual(u.identifier, "test@example.com")


class BaseQuotaTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        cls.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )

    def setUp(self):
        self.quota = Quota.objects.create(name="Test", size=2, event=self.event)
        self.item1 = Item.objects.create(event=self.event, name="Ticket", default_price=23)
        self.item2 = Item.objects.create(event=self.event, name="T-Shirt")
        p = Property.objects.create(event=self.event, name='Size')
        pv1 = PropertyValue.objects.create(prop=p, value='S')
        PropertyValue.objects.create(prop=p, value='M')
        PropertyValue.objects.create(prop=p, value='L')
        self.var1 = ItemVariation.objects.create(item=self.item2)
        self.var1.values.add(pv1)
        self.item2.properties.add(p)


class QuotaTestCase(BaseQuotaTestCase):

    def test_available(self):
        self.quota.items.add(self.item1)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 2))
        self.quota.items.add(self.item2)
        self.quota.variations.add(self.var1)
        try:
            self.item2.check_quotas()
            self.assertTrue(False)
        except:
            pass
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_OK, 2))

    def test_sold_out(self):
        self.quota.items.add(self.item1)
        order = Order.objects.create(event=self.event, status=Order.STATUS_PAID,
                                     expires=now() + timedelta(days=3),
                                     total=4)
        OrderPosition.objects.create(order=order, item=self.item1, price=2)
        OrderPosition.objects.create(order=order, item=self.item1, price=2)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_GONE, 0))

        self.quota.items.add(self.item2)
        self.quota.variations.add(self.var1)
        self.quota.size = 3
        self.quota.save()
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

        order = Order.objects.create(event=self.event, status=Order.STATUS_PAID,
                                     expires=now() + timedelta(days=3),
                                     total=4)
        OrderPosition.objects.create(order=order, item=self.item2, variation=self.var1, price=2)
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_GONE, 0))

    def test_ordered(self):
        self.quota.items.add(self.item1)
        order = Order.objects.create(event=self.event, status=Order.STATUS_PAID,
                                     expires=now() + timedelta(days=3),
                                     total=4)
        OrderPosition.objects.create(order=order, item=self.item1, price=2)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

        order = Order.objects.create(event=self.event, status=Order.STATUS_PENDING,
                                     expires=now() + timedelta(days=3),
                                     total=4)
        OrderPosition.objects.create(order=order, item=self.item1, price=2)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_ORDERED, 0))

        order.expires = now() - timedelta(days=3)
        order.save()
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

    def test_reserved(self):
        self.quota.items.add(self.item1)
        self.quota.size = 3
        self.quota.save()
        order = Order.objects.create(event=self.event, status=Order.STATUS_PAID,
                                     expires=now() + timedelta(days=3),
                                     total=4)
        OrderPosition.objects.create(order=order, item=self.item1, price=2)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 2))

        order = Order.objects.create(event=self.event, status=Order.STATUS_PENDING,
                                     expires=now() + timedelta(days=3),
                                     total=4)
        OrderPosition.objects.create(order=order, item=self.item1, price=2)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

        cp = CartPosition.objects.create(event=self.event, item=self.item1, price=2,
                                         expires=now() + timedelta(days=3))
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_RESERVED, 0))

        cp.expires = now() - timedelta(days=3)
        cp.save()
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

        self.quota.items.add(self.item2)
        self.quota.variations.add(self.var1)
        cp = CartPosition.objects.create(event=self.event, item=self.item2, variation=self.var1,
                                         price=2, expires=now() + timedelta(days=3))
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_RESERVED, 0))

    def test_multiple(self):
        self.quota.items.add(self.item1)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 2))

        quota2 = Quota.objects.create(event=self.event, name="Test 2", size=1)
        quota2.items.add(self.item1)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

        quota2.size = 0
        quota2.save()
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_GONE, 0))


class OrderTestCase(BaseQuotaTestCase):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_local_user(self.event, 'dummy', 'dummy')
        self.order = Order.objects.create(
            status=Order.STATUS_PENDING, event=self.event,
            user=self.user, datetime=now() - timedelta(days=5),
            expires=now() + timedelta(days=5), total=46
        )
        self.quota.items.add(self.item1)
        OrderPosition.objects.create(order=self.order, item=self.item1,
                                     variation=None, price=23)
        OrderPosition.objects.create(order=self.order, item=self.item1,
                                     variation=None, price=23)

    def test_paid_in_time(self):
        self.quota.size = 0
        self.quota.save()
        self.order.mark_paid()
        self.order = Order.objects.current.get(identity=self.order.identity)
        self.assertEqual(self.order.status, Order.STATUS_PAID)

    def test_paid_expired_available(self):
        self.order.expires = now() - timedelta(days=2)
        self.order.save()
        self.order.mark_paid()
        self.order = Order.objects.current.get(identity=self.order.identity)
        self.assertEqual(self.order.status, Order.STATUS_PAID)

    def test_paid_expired_partial(self):
        self.order.expires = now() - timedelta(days=2)
        self.order.save()
        self.quota.size = 1
        self.quota.save()
        try:
            self.order.mark_paid()
            self.assertFalse(True, 'This should have raised an exception.')
        except Quota.QuotaExceededException:
            pass
        self.order = Order.objects.current.get(identity=self.order.identity)
        self.assertIn(self.order.status, (Order.STATUS_PENDING, Order.STATUS_EXPIRED))

    def test_paid_expired_unavailable(self):
        self.order.expires = now() - timedelta(days=2)
        self.order.save()
        self.quota.size = 0
        self.quota.save()
        try:
            self.order.mark_paid()
            self.assertFalse(True, 'This should have raised an exception.')
        except Quota.QuotaExceededException:
            pass
        self.order = Order.objects.current.get(identity=self.order.identity)
        self.assertIn(self.order.status, (Order.STATUS_PENDING, Order.STATUS_EXPIRED))

    def test_paid_expired_unavailable_force(self):
        self.order.expires = now() - timedelta(days=2)
        self.order.save()
        self.quota.size = 0
        self.quota.save()
        self.order.mark_paid(force=True)
        self.order = Order.objects.current.get(identity=self.order.identity)
        self.assertEqual(self.order.status, Order.STATUS_PAID)
