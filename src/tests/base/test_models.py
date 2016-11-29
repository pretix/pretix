import datetime
import sys
from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import (
    CachedFile, CartPosition, Event, Item, ItemCategory, ItemVariation, Order,
    OrderPosition, Organizer, Question, Quota, User, Voucher,
)
from pretix.base.services.orders import (
    OrderError, cancel_order, mark_order_paid, perform_order,
)


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
        self.item3 = Item.objects.create(event=self.event, name="Goodie", default_price=23)
        self.var1 = ItemVariation.objects.create(item=self.item2, value='S')
        self.var2 = ItemVariation.objects.create(item=self.item2, value='M')
        self.var3 = ItemVariation.objects.create(item=self.item3, value='Fancy')


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
        self.assertTrue(v.is_active())

        v.block_quota = True
        v.save()
        self.assertEqual(self.item1.check_quotas(), (Quota.AVAILABILITY_ORDERED, 0))

    def test_voucher_variation(self):
        self.quota.variations.add(self.var1)
        self.quota.size = 1
        self.quota.save()

        v = Voucher.objects.create(item=self.item2, variation=self.var1, event=self.event)
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_OK, 1))
        self.assertTrue(v.is_active())

        v.block_quota = True
        v.save()
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_ORDERED, 0))

    def test_voucher_quota(self):
        self.quota.variations.add(self.var1)
        self.quota.size = 1
        self.quota.save()

        v = Voucher.objects.create(quota=self.quota, event=self.event)
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_OK, 1))
        self.assertTrue(v.is_active())

        v.block_quota = True
        v.save()
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_ORDERED, 0))

    def test_voucher_quota_multiuse(self):
        self.quota.size = 5
        self.quota.variations.add(self.var1)
        self.quota.save()
        Voucher.objects.create(quota=self.quota, event=self.event, block_quota=True, max_usages=5, redeemed=2)
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_OK, 2))
        Voucher.objects.create(quota=self.quota, event=self.event, block_quota=True, max_usages=2)
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_ORDERED, 0))

    def test_voucher_multiuse_count_overredeemed(self):
        if 'sqlite' not in settings.DATABASES['default']['ENGINE']:
            pytest.xfail('This should raise a type error on most databases')
        Voucher.objects.create(quota=self.quota, event=self.event, block_quota=True, max_usages=2, redeemed=4)
        self.assertEqual(self.quota.count_blocking_vouchers(), 0)

    def test_voucher_quota_multiuse_multiproduct(self):
        q2 = Quota.objects.create(event=self.event, name="foo", size=10)
        q2.items.add(self.item1)
        self.quota.size = 5
        self.quota.items.add(self.item1)
        self.quota.items.add(self.item2)
        self.quota.items.add(self.item3)
        self.quota.variations.add(self.var1)
        self.quota.variations.add(self.var2)
        self.quota.variations.add(self.var3)
        self.quota.save()
        Voucher.objects.create(item=self.item1, event=self.event, block_quota=True, max_usages=5, redeemed=2)
        Voucher.objects.create(item=self.item2, variation=self.var2, event=self.event, block_quota=True, max_usages=5,
                               redeemed=2)
        Voucher.objects.create(item=self.item2, variation=self.var2, event=self.event, block_quota=True, max_usages=5,
                               redeemed=2)
        self.assertEqual(self.quota.count_blocking_vouchers(), 9)

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
        v = Voucher.objects.create(quota=self.quota, event=self.event, valid_until=now() - timedelta(days=5),
                                   block_quota=True)
        self.assertEqual(self.var1.check_quotas(), (Quota.AVAILABILITY_OK, 1))
        self.assertFalse(v.is_active())

    def test_blocking_voucher_in_cart(self):
        self.quota.items.add(self.item1)
        v = Voucher.objects.create(quota=self.quota, event=self.event, valid_until=now() + timedelta(days=5),
                                   block_quota=True)
        CartPosition.objects.create(event=self.event, item=self.item1, price=2,
                                    expires=now() + timedelta(days=3), voucher=v)
        self.assertTrue(v.is_in_cart())
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

    def test_voucher_reuse(self):
        self.quota.items.add(self.item1)
        v = Voucher.objects.create(quota=self.quota, event=self.event, valid_until=now() + timedelta(days=5))
        self.assertTrue(v.is_active())
        self.assertFalse(v.is_in_cart())
        self.assertFalse(v.is_ordered())

        # use a voucher normally
        cart = CartPosition.objects.create(event=self.event, item=self.item1, price=self.item1.default_price,
                                           expires=now() + timedelta(days=3), voucher=v)
        self.assertTrue(v.is_active())
        self.assertTrue(v.is_in_cart())
        self.assertFalse(v.is_ordered())

        order = perform_order(event=self.event.id, payment_provider='free', positions=[cart.id])
        v.refresh_from_db()
        self.assertFalse(v.is_active())
        self.assertFalse(v.is_in_cart())
        self.assertTrue(v.is_ordered())

        # assert that the voucher cannot be reused
        cart = CartPosition.objects.create(event=self.event, item=self.item1, price=self.item1.default_price,
                                           expires=now() + timedelta(days=3), voucher=v)
        self.assertRaises(OrderError, perform_order, event=self.event.id, payment_provider='free', positions=[cart.id])

        # assert that the voucher can be re-used after cancelling the successful order
        cancel_order(order)
        v.refresh_from_db()
        self.assertTrue(v.is_active())
        self.assertFalse(v.is_in_cart())
        self.assertTrue(v.is_ordered())

        cart = CartPosition.objects.create(event=self.event, item=self.item1, price=self.item1.default_price,
                                           expires=now() + timedelta(days=3), voucher=v)
        perform_order(event=self.event.id, payment_provider='free', positions=[cart.id])

    def test_voucher_applicability_quota(self):
        self.quota.items.add(self.item1)
        v = Voucher.objects.create(quota=self.quota, event=self.event)
        self.assertTrue(v.applies_to(self.item1))
        self.assertFalse(v.applies_to(self.item2))

    def test_voucher_applicability_item(self):
        v = Voucher.objects.create(item=self.var1.item, event=self.event)
        self.assertFalse(v.applies_to(self.item1))
        self.assertTrue(v.applies_to(self.var1.item))
        self.assertTrue(v.applies_to(self.var1.item, self.var1))

    def test_voucher_applicability_variation(self):
        v = Voucher.objects.create(item=self.var1.item, variation=self.var1, event=self.event)
        self.assertFalse(v.applies_to(self.item1))
        self.assertFalse(v.applies_to(self.var1.item))
        self.assertTrue(v.applies_to(self.var1.item, self.var1))
        self.assertFalse(v.applies_to(self.var1.item, self.var2))

    def test_voucher_no_item_with_quota(self):
        with self.assertRaises(ValidationError):
            v = Voucher(quota=self.quota, item=self.item1, event=self.event)
            v.clean()

    def test_voucher_item_with_no_variation(self):
        with self.assertRaises(ValidationError):
            v = Voucher(item=self.item1, variation=self.var1, event=self.event)
            v.clean()

    def test_voucher_item_does_not_match_variation(self):
        with self.assertRaises(ValidationError):
            v = Voucher(item=self.item2, variation=self.var3, event=self.event)
            v.clean()

    def test_voucher_specify_variation_for_block_quota(self):
        with self.assertRaises(ValidationError):
            v = Voucher(item=self.item2, block_quota=True, event=self.event)
            v.clean()

    def test_voucher_no_item_but_variation(self):
        with self.assertRaises(ValidationError):
            v = Voucher(variation=self.var1, event=self.event)
            v.clean()


class VoucherTestCase(BaseQuotaTestCase):

    def test_calculate_price_none(self):
        v = Voucher.objects.create(event=self.event, price_mode='none', value=Decimal('10.00'))
        v.calculate_price(Decimal('23.42')) == Decimal('23.42')

    def test_calculate_price_set_empty(self):
        v = Voucher.objects.create(event=self.event, price_mode='set')
        v.calculate_price(Decimal('23.42')) == Decimal('23.42')

    def test_calculate_price_set(self):
        v = Voucher.objects.create(event=self.event, price_mode='set', value=Decimal('10.00'))
        v.calculate_price(Decimal('23.42')) == Decimal('10.00')

    def test_calculate_price_subtract(self):
        v = Voucher.objects.create(event=self.event, price_mode='subtract', value=Decimal('10.00'))
        v.calculate_price(Decimal('23.42')) == Decimal('13.42')

    def test_calculate_price_percent(self):
        v = Voucher.objects.create(event=self.event, price_mode='percent', value=Decimal('23.00'))
        v.calculate_price(Decimal('100.00')) == Decimal('77.00')


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
        self.event.settings.payment_term_last = (now() + timedelta(days=2)).strftime('%Y-%m-%d')
        self.order.status = Order.STATUS_EXPIRED
        self.order.expires = now() - timedelta(days=2)
        self.order.save()
        mark_order_paid(self.order)
        self.order = Order.objects.get(id=self.order.id)
        self.assertEqual(self.order.status, Order.STATUS_PAID)

    def test_paid_expired_after_last_date(self):
        self.event.settings.payment_term_last = (now() - timedelta(days=2)).strftime('%Y-%m-%d')
        self.order.status = Order.STATUS_EXPIRED
        self.order.expires = now() - timedelta(days=2)
        self.order.save()
        with self.assertRaises(Quota.QuotaExceededException):
            mark_order_paid(self.order)
        self.order = Order.objects.get(id=self.order.id)
        self.assertEqual(self.order.status, Order.STATUS_EXPIRED)

    def test_paid_expired_late_not_allowed(self):
        self.event.settings.payment_term_accept_late = False
        self.order.status = Order.STATUS_EXPIRED
        self.order.expires = now() - timedelta(days=2)
        self.order.save()
        with self.assertRaises(Quota.QuotaExceededException):
            mark_order_paid(self.order)
        self.order = Order.objects.get(id=self.order.id)
        self.assertEqual(self.order.status, Order.STATUS_EXPIRED)

    def test_paid_expired_unavailable(self):
        self.order.expires = now() - timedelta(days=2)
        self.order.status = Order.STATUS_EXPIRED
        self.order.save()
        self.quota.size = 0
        self.quota.save()
        with self.assertRaises(Quota.QuotaExceededException):
            mark_order_paid(self.order)
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


class EventTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizer = Organizer.objects.create(name='Dummy', slug='dummy')

    def test_event_end_before_start(self):
        event = Event(
            organizer=self.organizer, name='Dummy', slug='dummy',
            date_from=now(), date_to=now() - timedelta(hours=1)
        )
        with self.assertRaises(ValidationError) as context:
            event.clean()

        self.assertIn('date_to', str(context.exception))

    def test_presale_end_before_start(self):
        event = Event(
            organizer=self.organizer, name='Dummy', slug='dummy',
            presale_start=now(), presale_end=now() - timedelta(hours=1)
        )
        with self.assertRaises(ValidationError) as context:
            event.clean()

        self.assertIn('presale_end', str(context.exception))

    def test_slug_validation(self):
        event = Event(
            organizer=self.organizer, name='Download', slug='download',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc)
        )
        with self.assertRaises(ValidationError) as context:
            event.full_clean()

        self.assertIn('slug', str(context.exception))


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
