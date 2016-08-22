import sys
from datetime import timedelta

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import (
    CachedFile, CartPosition, Event, Item, ItemCategory, ItemVariation, Order,
    OrderPosition, Organizer, Question, Quota, User, Voucher,
)
from pretix.base.services.orders import mark_order_paid


class UserTestCase(TestCase):
    def test_name(self):
        u = User.objects.create_user('test@foo.bar', 'test')
        u.givenname = "Christopher"
        u.familyname = "Nolan"
        u.set_password("test")
        u.save()
        self.assertEqual(u.get_full_name(), 'Nolan, Christopher')
        self.assertEqual(u.get_short_name(), 'Christopher')
        u.givenname = None
        u.save()
        self.assertEqual(u.get_full_name(), 'Nolan')
        self.assertEqual(u.get_short_name(), 'Nolan')
        u.givenname = "Christopher"
        u.familyname = None
        u.save()
        self.assertEqual(u.get_full_name(), 'Christopher')
        self.assertEqual(u.get_short_name(), 'Christopher')
        u.givenname = None
        u.save()
        self.assertEqual(u.get_full_name(), 'test@foo.bar')
        self.assertEqual(u.get_short_name(), 'test@foo.bar')


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
        self.item1 = Item.objects.create(event=self.event, name="Ticket", default_price=23,
                                         admission=True)
        self.item2 = Item.objects.create(event=self.event, name="T-Shirt", default_price=23)
        self.var1 = ItemVariation.objects.create(item=self.item2, value='S')


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
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_ORDERED, 0))

        order.status = Order.STATUS_EXPIRED
        order.save()
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

    def test_ordered_multi_quota(self):
        quota2 = Quota.objects.create(name="Test", size=2, event=self.event)
        quota2.items.add(self.item2)
        quota2.variations.add(self.var1)
        self.quota.items.add(self.item2)
        self.quota.variations.add(self.var1)

        order = Order.objects.create(event=self.event, status=Order.STATUS_PAID,
                                     expires=now() + timedelta(days=3),
                                     total=4)
        OrderPosition.objects.create(order=order, item=self.item2, variation=self.var1, price=2)

        self.assertEqual(quota2.availability(), (Quota.AVAILABILITY_OK, 1))

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

    def test_ignore_quotas(self):
        self.quota.items.add(self.item1)
        quota2 = Quota.objects.create(event=self.event, name="Test 2", size=0)
        quota2.items.add(self.item1)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_GONE, 0))
        self.assertEqual(self.item1.check_quotas(ignored_quotas=[quota2]), (Quota.AVAILABILITY_OK, 2))
        self.assertEqual(self.item1.check_quotas(ignored_quotas=[self.quota, quota2]),
                         (Quota.AVAILABILITY_OK, sys.maxsize))

    def test_unlimited(self):
        self.quota.items.add(self.item1)
        order = Order.objects.create(event=self.event, status=Order.STATUS_PAID,
                                     expires=now() + timedelta(days=3),
                                     total=2)
        OrderPosition.objects.create(order=order, item=self.item1, price=2)
        OrderPosition.objects.create(order=order, item=self.item1, price=2)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_GONE, 0))

        self.quota.size = None
        self.quota.save()
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, None))

    def test_voucher_product(self):
        self.quota.items.add(self.item1)
        self.quota.size = 1
        self.quota.save()

        v = Voucher.objects.create(item=self.item1, event=self.event)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

        v.block_quota = True
        v.save()
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_ORDERED, 0))

    def test_voucher_variation(self):
        self.quota.variations.add(self.var1)
        self.quota.size = 1
        self.quota.save()

        v = Voucher.objects.create(item=self.item2, variation=self.var1, event=self.event)
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

        v.block_quota = True
        v.save()
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_ORDERED, 0))

    def test_voucher_quota(self):
        self.quota.variations.add(self.var1)
        self.quota.size = 1
        self.quota.save()

        v = Voucher.objects.create(quota=self.quota, event=self.event)
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

        v.block_quota = True
        v.save()
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_ORDERED, 0))

    def test_voucher_quota_expiring_soon(self):
        self.quota.variations.add(self.var1)
        self.quota.size = 1
        self.quota.save()
        Voucher.objects.create(quota=self.quota, event=self.event, valid_until=now() + timedelta(days=5),
                               block_quota=True)
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_ORDERED, 0))

    def test_voucher_quota_expired(self):
        self.quota.variations.add(self.var1)
        self.quota.size = 1
        self.quota.save()
        Voucher.objects.create(quota=self.quota, event=self.event, valid_until=now() - timedelta(days=5),
                               block_quota=True)
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

    def test_blocking_voucher_in_cart(self):
        self.quota.items.add(self.item1)
        v = Voucher.objects.create(quota=self.quota, event=self.event, valid_until=now() + timedelta(days=5),
                                   block_quota=True)
        CartPosition.objects.create(event=self.event, item=self.item1, price=2,
                                    expires=now() + timedelta(days=3), voucher=v)
        self.assertEqual(self.quota.count_blocking_vouchers(), 1)
        self.assertEqual(self.quota.count_in_cart(), 0)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

    def test_blocking_voucher_in_cart_inifinitely_valid(self):
        self.quota.items.add(self.item1)
        v = Voucher.objects.create(quota=self.quota, event=self.event, block_quota=True)
        CartPosition.objects.create(event=self.event, item=self.item1, price=2,
                                    expires=now() + timedelta(days=3), voucher=v)
        self.assertEqual(self.quota.count_blocking_vouchers(), 1)
        self.assertEqual(self.quota.count_in_cart(), 0)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

    def test_blocking_expired_voucher_in_cart(self):
        self.quota.items.add(self.item1)
        v = Voucher.objects.create(quota=self.quota, event=self.event, valid_until=now() - timedelta(days=5),
                                   block_quota=True)
        CartPosition.objects.create(event=self.event, item=self.item1, price=2,
                                    expires=now() + timedelta(days=3), voucher=v)
        self.assertEqual(self.quota.count_blocking_vouchers(), 0)
        self.assertEqual(self.quota.count_in_cart(), 1)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 1))

    def test_nonblocking_voucher_in_cart(self):
        self.quota.items.add(self.item1)
        v = Voucher.objects.create(quota=self.quota, event=self.event)
        CartPosition.objects.create(event=self.event, item=self.item1, price=2,
                                    expires=now() + timedelta(days=3), voucher=v)
        self.assertEqual(self.quota.count_blocking_vouchers(), 0)
        self.assertEqual(self.quota.count_in_cart(), 1)
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_OK, 1))


class OrderTestCase(BaseQuotaTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.order = Order.objects.create(
            status=Order.STATUS_PENDING, event=self.event,
            datetime=now() - timedelta(days=5),
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
        mark_order_paid(self.order)
        self.order = Order.objects.get(id=self.order.id)
        self.assertEqual(self.order.status, Order.STATUS_PAID)

    def test_paid_expired_available(self):
        self.order.status = Order.STATUS_EXPIRED
        self.order.expires = now() - timedelta(days=2)
        self.order.save()
        mark_order_paid(self.order)
        self.order = Order.objects.get(id=self.order.id)
        self.assertEqual(self.order.status, Order.STATUS_PAID)

    def test_paid_expired_partial(self):
        self.order.status = Order.STATUS_EXPIRED
        self.order.expires = now() - timedelta(days=2)
        self.order.save()
        self.quota.size = 1
        self.quota.save()
        try:
            mark_order_paid(self.order)
            self.assertFalse(True, 'This should have raised an exception.')
        except Quota.QuotaExceededException:
            pass
        self.order = Order.objects.get(id=self.order.id)
        self.assertIn(self.order.status, (Order.STATUS_PENDING, Order.STATUS_EXPIRED))

    def test_paid_expired_unavailable(self):
        self.order.expires = now() - timedelta(days=2)
        self.order.status = Order.STATUS_EXPIRED
        self.order.save()
        self.quota.size = 0
        self.quota.save()
        try:
            mark_order_paid(self.order)
            self.assertFalse(True, 'This should have raised an exception.')
        except Quota.QuotaExceededException:
            pass
        self.order = Order.objects.get(id=self.order.id)
        self.assertIn(self.order.status, (Order.STATUS_PENDING, Order.STATUS_EXPIRED))

    def test_paid_after_deadline_but_not_expired(self):
        self.order.expires = now() - timedelta(days=2)
        self.order.save()
        mark_order_paid(self.order)
        self.order = Order.objects.get(id=self.order.id)
        self.assertEqual(self.order.status, Order.STATUS_PAID)

    def test_paid_expired_unavailable_force(self):
        self.order.expires = now() - timedelta(days=2)
        self.order.save()
        self.quota.size = 0
        self.quota.save()
        mark_order_paid(self.order, force=True)
        self.order = Order.objects.get(id=self.order.id)
        self.assertEqual(self.order.status, Order.STATUS_PAID)

    def test_can_modify_answers(self):
        self.event.settings.set('invoice_address_asked', False)
        self.event.settings.set('attendee_names_asked', True)
        assert self.order.can_modify_answers
        self.event.settings.set('attendee_names_asked', False)
        assert not self.order.can_modify_answers
        self.event.settings.set('invoice_address_asked', True)
        assert self.order.can_modify_answers
        q = Question.objects.create(question='Foo', type=Question.TYPE_BOOLEAN, event=self.event)
        self.item1.questions.add(q)
        assert self.order.can_modify_answers
        self.order.status = Order.STATUS_REFUNDED
        assert not self.order.can_modify_answers
        self.order.status = Order.STATUS_PAID
        assert self.order.can_modify_answers
        self.event.settings.set('last_order_modification_date', now() - timedelta(days=1))
        assert not self.order.can_modify_answers

    def test_can_cancel_order(self):
        item1 = Item.objects.create(event=self.event, name="Ticket", default_price=23,
                                    admission=True, allow_cancel=True)
        OrderPosition.objects.create(order=self.order, item=item1,
                                     variation=None, price=23)
        assert self.order.can_user_cancel

    def test_can_cancel_order_multiple(self):
        item1 = Item.objects.create(event=self.event, name="Ticket", default_price=23,
                                    admission=True, allow_cancel=True)
        item2 = Item.objects.create(event=self.event, name="Ticket", default_price=23,
                                    admission=True, allow_cancel=True)
        OrderPosition.objects.create(order=self.order, item=item1,
                                     variation=None, price=23)
        OrderPosition.objects.create(order=self.order, item=item2,
                                     variation=None, price=23)
        assert self.order.can_user_cancel

    def test_can_not_cancel_order(self):
        item1 = Item.objects.create(event=self.event, name="Ticket", default_price=23,
                                    admission=True, allow_cancel=False)
        OrderPosition.objects.create(order=self.order, item=item1,
                                     variation=None, price=23)
        assert self.order.can_user_cancel is False

    def test_can_not_cancel_order_multiple(self):
        item1 = Item.objects.create(event=self.event, name="Ticket", default_price=23,
                                    admission=True, allow_cancel=False)
        item2 = Item.objects.create(event=self.event, name="Ticket", default_price=23,
                                    admission=True, allow_cancel=True)
        OrderPosition.objects.create(order=self.order, item=item1,
                                     variation=None, price=23)
        OrderPosition.objects.create(order=self.order, item=item2,
                                     variation=None, price=23)
        assert self.order.can_user_cancel is False

    def test_can_not_cancel_order_multiple_mixed(self):
        item1 = Item.objects.create(event=self.event, name="Ticket", default_price=23,
                                    admission=True, allow_cancel=False)
        item2 = Item.objects.create(event=self.event, name="Ticket", default_price=23,
                                    admission=True, allow_cancel=True)
        OrderPosition.objects.create(order=self.order, item=item1,
                                     variation=None, price=23)
        OrderPosition.objects.create(order=self.order, item=item2,
                                     variation=None, price=23)
        assert self.order.can_user_cancel is False


class ItemCategoryTest(TestCase):
    """
    This test case tests various methods around the category model.
    """

    @classmethod
    def setUpTestData(cls):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        cls.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )

    def test_sorting(self):
        c1 = ItemCategory.objects.create(event=self.event)
        c2 = ItemCategory.objects.create(event=self.event)
        assert c1 < c2
        c1.position = 2
        c2.position = 1
        assert c2 < c1
        assert not c1 < c2
        assert c1 > c2
        c1.position = 1
        c2.position = 2
        assert c1 < c2
        assert c2 > c1


class ItemTest(TestCase):
    """
    This test case tests various methods around the item model.
    """

    @classmethod
    def setUpTestData(cls):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        cls.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )

    def test_is_available(self):
        i = Item.objects.create(
            event=self.event, name="Ticket", default_price=23,
            active=True, available_until=now() + timedelta(days=1),
        )
        assert i.is_available()
        i.available_from = now() - timedelta(days=1)
        assert i.is_available()
        i.available_from = now() + timedelta(days=1)
        i.available_until = None
        assert not i.is_available()
        i.available_from = None
        i.available_until = now() - timedelta(days=1)
        assert not i.is_available()
        i.available_from = None
        i.available_until = None
        assert i.is_available()
        i.active = False
        assert not i.is_available()


class CachedFileTestCase(TestCase):
    def test_file_handling(self):
        cf = CachedFile()
        val = SimpleUploadedFile("testfile.txt", b"file_content")
        cf.file.save("testfile.txt", val)
        cf.type = "text/plain"
        cf.filename = "testfile.txt"
        cf.save()
        assert default_storage.exists(cf.file.name)
        with default_storage.open(cf.file.name, 'r') as f:
            assert f.read().strip() == "file_content"
        cf.delete()
        assert not default_storage.exists(cf.file.name)
