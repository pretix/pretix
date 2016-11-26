import datetime
from decimal import Decimal

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils.timezone import now
from tests.base import SoupTest

from pretix.base.models import (
    Event, EventPermission, Item, ItemCategory, ItemVariation, Order,
    Organizer, Quota, User,
)


class EventTestMixin:
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            live=True
        )
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        EventPermission.objects.create(user=self.user, event=self.event)


class EventMiddlewareTest(EventTestMixin, SoupTest):
    def test_event_header(self):
        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn(str(self.event.name), doc.find("h1").text)

    def test_not_found(self):
        resp = self.client.get('/%s/%s/' % ('foo', 'bar'))
        self.assertEqual(resp.status_code, 404)

    def test_not_live(self):
        self.event.live = False
        self.event.save()
        resp = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertEqual(resp.status_code, 403)

    def test_not_live_logged_in(self):
        self.event.live = False
        self.event.save()

        self.client.login(email='dummy@dummy.dummy', password='dummy')
        resp = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertEqual(resp.status_code, 200)


class ItemDisplayTest(EventTestMixin, SoupTest):
    def test_not_active(self):
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=False)
        q.items.add(item)
        html = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", html)
        self.assertNotIn("btn-add-to-cart", html)

    def test_without_category(self):
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True)
        q.items.add(item)
        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", doc.select("section .product-row")[0].text)
        self.assertEqual(len(doc.select("#btn-add-to-cart")), 1)

    def test_timely_available(self):
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True,
                                   available_until=now() + datetime.timedelta(days=2),
                                   available_from=now() - datetime.timedelta(days=2))
        q.items.add(item)
        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", doc.select("body")[0].text)

    def test_no_longer_available(self):
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True,
                                   available_until=now() - datetime.timedelta(days=2))
        q.items.add(item)
        html = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", html)

    def test_not_yet_available(self):
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True,
                                   available_from=now() + datetime.timedelta(days=2))
        q.items.add(item)
        html = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", html)

    def test_hidden_without_voucher(self):
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True,
                                   hide_without_voucher=True)
        q.items.add(item)
        html = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", html)

    def test_simple_with_category(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
        q.items.add(item)
        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Entry tickets", doc.select("section:nth-of-type(1) h3")[0].text)
        self.assertIn("Early-bird", doc.select("section:nth-of-type(1) div:nth-of-type(1)")[0].text)

    def test_simple_without_quota(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
        resp = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", resp.rendered_content)

    def test_no_variations_in_quota(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
        ItemVariation.objects.create(item=item, value='Blue')
        q.items.add(item)
        resp = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", resp.rendered_content)

    def test_one_variation_in_quota(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
        var1 = ItemVariation.objects.create(item=item, value='Red')
        ItemVariation.objects.create(item=item, value='Blue')
        q.items.add(item)
        q.variations.add(var1)
        self._assert_variation_found()

    def test_one_variation_in_unlimited_quota(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        q = Quota.objects.create(event=self.event, name='Quota', size=None)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
        var1 = ItemVariation.objects.create(item=item, value='Red')
        ItemVariation.objects.create(item=item, value='Blue')
        q.items.add(item)
        q.variations.add(var1)
        self._assert_variation_found()

    def _assert_variation_found(self):
        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", doc.select("section:nth-of-type(1) div:nth-of-type(1)")[0].text)
        self.assertIn("Red", doc.select("section:nth-of-type(1)")[0].text)
        self.assertNotIn("Black", doc.select("section:nth-of-type(1)")[0].text)

    def test_variation_prices_in_quota(self):
        c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=12)
        var1 = ItemVariation.objects.create(item=item, value='Red', default_price=14, position=1)
        var2 = ItemVariation.objects.create(item=item, value='Black', position=2)
        q.variations.add(var1)
        q.variations.add(var2)
        q.items.add(item)
        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", doc.select("section:nth-of-type(1) div:nth-of-type(1)")[0].text)
        self.assertIn("Red", doc.select("section:nth-of-type(1) div.variation")[0].text)
        self.assertIn("14.00", doc.select("section:nth-of-type(1) div.variation")[0].text)
        self.assertIn("Black", doc.select("section:nth-of-type(1) div.variation")[1].text)
        self.assertIn("12.00", doc.select("section:nth-of-type(1) div.variation")[1].text)


class VoucherRedeemItemDisplayTest(EventTestMixin, SoupTest):
    def setUp(self):
        super().setUp()
        self.q = Quota.objects.create(event=self.event, name='Quota', size=2)
        self.v = self.event.vouchers.create(quota=self.q)
        self.item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=Decimal('12.00'),
                                        active=True)
        self.q.items.add(self.item)

    def test_not_active(self):
        self.item.active = False
        self.item.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "Early-bird" not in html.rendered_content

    def test_not_in_quota(self):
        q2 = Quota.objects.create(event=self.event, name='Quota', size=2)
        self.v.quota = q2
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "Early-bird" not in html.rendered_content

    def test_in_quota(self):
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "Early-bird" in html.rendered_content
        assert "12.00" in html.rendered_content

    def test_specific_item(self):
        self.v.item = self.item
        self.v.quota = None
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "Early-bird" in html.rendered_content

    def test_hide_wo_voucher_quota(self):
        self.item.hide_without_voucher = True
        self.item.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "Early-bird" not in html.rendered_content

    def test_hide_without_voucher_item(self):
        self.item.hide_without_voucher = True
        self.item.save()
        self.v.item = self.item
        self.v.quota = None
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "Early-bird" in html.rendered_content

    def test_variations_all(self):
        var1 = ItemVariation.objects.create(item=self.item, value='Red', default_price=14, position=1)
        var2 = ItemVariation.objects.create(item=self.item, value='Black', position=2)
        self.q.variations.add(var1)
        self.q.variations.add(var2)
        self.v.item = self.item
        self.v.quota = None
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "Red" in html.rendered_content
        assert "Black" in html.rendered_content

    def test_variations_specific(self):
        var1 = ItemVariation.objects.create(item=self.item, value='Red', default_price=14, position=1)
        var2 = ItemVariation.objects.create(item=self.item, value='Black', position=2)
        self.q.variations.add(var1)
        self.q.variations.add(var2)
        self.v.item = self.item
        self.v.variation = var1
        self.v.quota = None
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "Red" in html.rendered_content
        assert "Black" not in html.rendered_content

    def test_sold_out(self):
        self.q.size = 0
        self.q.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "_voucher_item" not in html.rendered_content

    def test_sold_out_blocking(self):
        self.q.size = 0
        self.q.save()
        self.v.block_quota = True
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "_voucher_item" in html.rendered_content

    def test_sold_out_ignore(self):
        self.q.size = 0
        self.q.save()
        self.v.allow_ignore_quota = True
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "_voucher_item" in html.rendered_content

    def test_variations_sold_out(self):
        var1 = ItemVariation.objects.create(item=self.item, value='Red', default_price=14, position=1)
        var2 = ItemVariation.objects.create(item=self.item, value='Black', position=2)
        self.q.variations.add(var1)
        self.q.variations.add(var2)
        self.q.size = 0
        self.q.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "_voucher_item" not in html.rendered_content

    def test_variations_sold_out_blocking(self):
        var1 = ItemVariation.objects.create(item=self.item, value='Red', default_price=14, position=1)
        var2 = ItemVariation.objects.create(item=self.item, value='Black', position=2)
        self.q.variations.add(var1)
        self.q.variations.add(var2)
        self.q.size = 0
        self.q.save()
        self.v.block_quota = True
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "_voucher_item" in html.rendered_content

    def test_special_price(self):
        self.v.price = Decimal("10.00")
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "Early-bird" in html.rendered_content
        assert "10.00" in html.rendered_content

    def test_special_price_variations(self):
        var1 = ItemVariation.objects.create(item=self.item, value='Red', default_price=14, position=1)
        var2 = ItemVariation.objects.create(item=self.item, value='Black', position=2)
        self.q.variations.add(var1)
        self.q.variations.add(var2)
        self.v.price = Decimal("10.00")
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "Early-bird" in html.rendered_content
        assert "10.00" in html.rendered_content
        assert "14.00" not in html.rendered_content

    def test_fail_redeemed(self):
        self.v.redeemed = 1
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code), follow=True)
        assert "alert-danger" in html.rendered_content

    def test_fail_expired(self):
        self.v.valid_until = now() - datetime.timedelta(days=1)
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code), follow=True)
        assert "alert-danger" in html.rendered_content

    def test_fail_unknown(self):
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, 'ABC'), follow=True)
        assert "alert-danger" in html.rendered_content

    def test_not_yet_started(self):
        self.event.presale_start = now() + datetime.timedelta(days=1)
        self.event.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, 'ABC'), follow=True)
        assert "alert-danger" in html.rendered_content

    def test_over(self):
        self.event.presale_end = now() - datetime.timedelta(days=1)
        self.event.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, 'ABC'), follow=True)
        assert "alert-danger" in html.rendered_content


class DeadlineTest(EventTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        self.item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=False)
        q.items.add(self.item)

    def test_not_yet_started(self):
        self.event.presale_start = now() + datetime.timedelta(days=1)
        self.event.save()
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('alert-info', response.rendered_content)
        self.assertNotIn('btn-add-to-cart', response.rendered_content)
        response = self.client.post(
            '/%s/%s/cart/add' % (self.orga.slug, self.event.slug),
            {
                'item_%d' % self.item.id: '1',
            },
            follow=True
        )
        self.assertIn('alert-danger', response.rendered_content)
        self.assertIn('not yet started', response.rendered_content)

    def test_over(self):
        self.event.presale_end = now() - datetime.timedelta(days=1)
        self.event.save()
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('alert-info', response.rendered_content)
        self.assertNotIn('btn-add-to-cart', response.rendered_content)
        response = self.client.post(
            '/%s/%s/cart/add' % (self.orga.slug, self.event.slug),
            {
                'item_%d' % self.item.id: '1'
            },
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
        self.assertNotIn('btn-add-to-cart', response.rendered_content)
        response = self.client.post(
            '/%s/%s/cart/add' % (self.orga.slug, self.event.slug),
            {
                'item_%d' % self.item.id: '1'
            }
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
        self.assertNotIn('btn-add-to-cart', response.rendered_content)
        response = self.client.post(
            '/%s/%s/cart/add' % (self.orga.slug, self.event.slug),
            {
                'item_%d' % self.item.id: '1'
            }
        )
        self.assertNotEqual(response.status_code, 403)


class TestResendLink(EventTestMixin, SoupTest):
    def test_no_orders(self):
        mail.outbox = []
        url = '/{}/{}/resend/'.format(self.orga.slug, self.event.slug)
        resp = self.client.post(url, data={'email': 'dummy@dummy.dummy'})

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_no_orders_from_user(self):
        Order.objects.create(
            code='DUMMY1', status=Order.STATUS_PENDING, event=self.event,
            email='dummy@dummy.dummy', datetime=now(), expires=now(),
            total=0,
        )
        mail.outbox = []
        url = '/{}/{}/resend/'.format(self.orga.slug, self.event.slug)
        resp = self.client.post(url, data={'email': 'dummy@dummy.different'})

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_one_order(self):
        Order.objects.create(
            code='DUMMY1', status=Order.STATUS_PENDING, event=self.event,
            email='dummy@dummy.dummy', datetime=now(), expires=now(),
            total=0,
        )
        mail.outbox = []
        url = '/{}/{}/resend/'.format(self.orga.slug, self.event.slug)
        resp = self.client.post(url, data={'email': 'dummy@dummy.dummy'})

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('DUMMY1', mail.outbox[0].body)

    def test_multiple_orders(self):
        Order.objects.create(
            code='DUMMY1', status=Order.STATUS_PENDING, event=self.event,
            email='dummy@dummy.dummy', datetime=now(), expires=now(),
            total=0,
        )
        Order.objects.create(
            code='DUMMY2', status=Order.STATUS_PENDING, event=self.event,
            email='dummy@dummy.dummy', datetime=now(), expires=now(),
            total=0,
        )
        mail.outbox = []
        url = '/{}/{}/resend/'.format(self.orga.slug, self.event.slug)
        resp = self.client.post(url, data={'email': 'dummy@dummy.dummy'})

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('DUMMY1', mail.outbox[0].body)
        self.assertIn('DUMMY2', mail.outbox[0].body)


class EventSlugBlacklistValidatorTest(EventTestMixin, SoupTest):
    def test_slug_validation(self):
        event = Event(
            organizer=self.orga,
            name='download',
            slug='download',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            live=True
        )
        with self.assertRaises(ValidationError):
            if event.full_clean():
                event.save()

        self.assertEqual(Event.objects.filter(name='download').count(), 0)
