import datetime
import re
from decimal import Decimal

from django.conf import settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils.timezone import now
from pytz import timezone
from tests.base import SoupTest

from pretix.base.models import (
    Event, Item, ItemCategory, ItemVariation, Order, Organizer, Quota, Team,
    User, WaitingListEntry,
)
from pretix.base.models.items import SubEventItem


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
        t = Team.objects.create(organizer=self.orga, can_change_event_settings=True)
        t.members.add(self.user)
        t.limit_events.add(self.event)


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

    def test_not_found_event(self):
        resp = self.client.get('/%s/%s/ical' % ('foo', 'bar'))
        self.assertEqual(resp.status_code, 404)

    def test_mandatory_field(self):
        self.event.date_to = self.event.date_from + datetime.timedelta(days=2)
        self.event.save()
        resp = self.client.get('/%s/%s/ical' % (self.orga.slug, self.event.slug))
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

    def test_subevents(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
        se2 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
        q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se1)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0)
        q.items.add(item)

        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se1.pk))
        self.assertIn("Early-bird", resp.rendered_content)
        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se2.pk))
        self.assertNotIn("Early-bird", resp.rendered_content)

    def test_subevent_prices(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
        se2 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=15)
        q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se1)
        q.items.add(item)
        q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se2)
        q.items.add(item)
        SubEventItem.objects.create(subevent=se1, item=item, price=12)

        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se1.pk))
        self.assertIn("12.00", resp.rendered_content)
        self.assertNotIn("15.00", resp.rendered_content)
        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se2.pk))
        self.assertIn("15.00", resp.rendered_content)
        self.assertNotIn("12.00", resp.rendered_content)

    def test_subevent_net_prices(self):
        self.event.has_subevents = True
        self.event.save()
        self.event.settings.display_net_prices = True
        se1 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
        se2 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
        item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=15,
                                   tax_rate=19)
        q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se1)
        q.items.add(item)
        q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se2)
        q.items.add(item)
        SubEventItem.objects.create(subevent=se1, item=item, price=12)

        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se1.pk))
        self.assertIn("10.08", resp.rendered_content)
        self.assertNotIn("12.00", resp.rendered_content)
        self.assertNotIn("15.00", resp.rendered_content)
        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se2.pk))
        self.assertIn("12.61", resp.rendered_content)
        self.assertNotIn("12.00", resp.rendered_content)
        self.assertNotIn("15.00", resp.rendered_content)

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

    def test_voucher_price(self):
        self.v.value = Decimal("10.00")
        self.v.price_mode = 'set'
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "Early-bird" in html.rendered_content
        assert "10.00" in html.rendered_content

    def test_voucher_price_percentage(self):
        self.v.value = Decimal("10.00")
        self.v.price_mode = 'percent'
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "Early-bird" in html.rendered_content
        assert "10.80" in html.rendered_content

    def test_voucher_price_variations(self):
        var1 = ItemVariation.objects.create(item=self.item, value='Red', default_price=14, position=1)
        var2 = ItemVariation.objects.create(item=self.item, value='Black', position=2)
        self.q.variations.add(var1)
        self.q.variations.add(var2)
        self.v.value = Decimal("10.00")
        self.v.price_mode = 'set'
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


class WaitingListTest(EventTestMixin, SoupTest):
    def setUp(self):
        super().setUp()
        self.q = Quota.objects.create(event=self.event, name='Quota', size=0)
        self.v = self.event.vouchers.create(quota=self.q)
        self.item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=Decimal('12.00'),
                                        active=True)
        self.q.items.add(self.item)
        self.event.settings.set('waiting_list_enabled', True)

    def test_disabled(self):
        self.event.settings.set('waiting_list_enabled', False)
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('waitinglist', response.rendered_content)
        response = self.client.get(
            '/%s/%s/waitinglist?item=%d' % (self.orga.slug, self.event.slug, self.item.pk + 1)
        )
        self.assertEqual(response.status_code, 302)

    def test_display_link(self):
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('waitinglist', response.rendered_content)

    def test_submit_form(self):
        response = self.client.get(
            '/%s/%s/waitinglist?item=%d' % (self.orga.slug, self.event.slug, self.item.pk)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('waiting list', response.rendered_content)
        response = self.client.post(
            '/%s/%s/waitinglist?item=%d' % (self.orga.slug, self.event.slug, self.item.pk), {
                'email': 'foo@bar.com'
            }
        )
        self.assertEqual(response.status_code, 302)
        wle = WaitingListEntry.objects.get(email='foo@bar.com')
        assert wle.event == self.event
        assert wle.item == self.item
        assert wle.variation is None
        assert wle.voucher is None
        assert wle.locale == 'en'

    def test_invalid_item(self):
        response = self.client.get(
            '/%s/%s/waitinglist?item=%d' % (self.orga.slug, self.event.slug, self.item.pk + 1)
        )
        self.assertEqual(response.status_code, 302)

    def test_available(self):
        self.q.size = 1
        self.q.save()
        response = self.client.post(
            '/%s/%s/waitinglist?item=%d' % (self.orga.slug, self.event.slug, self.item.pk), {
                'email': 'foo@bar.com'
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(WaitingListEntry.objects.filter(email='foo@bar.com').exists())


class DeadlineTest(EventTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        q = Quota.objects.create(event=self.event, name='Quota', size=2)
        self.item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True)
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
        self.assertIn('btn-add-to-cart', response.rendered_content)
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
        self.assertIn('btn-add-to-cart', response.rendered_content)
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


class EventIcalDownloadTest(EventTestMixin, SoupTest):
    def setUp(self):
        super().setUp()
        self.event.settings.show_date_to = True
        self.event.settings.show_times = True
        self.event.location = 'DUMMY ARENA'
        self.event.date_from = datetime.datetime(2013, 12, 26, 21, 57, 58, tzinfo=datetime.timezone.utc)
        self.event.date_to = self.event.date_from + datetime.timedelta(days=2)
        self.event.settings.timezone = 'UTC'
        self.event.save()

    def test_response_type(self):
        ical = self.client.get('/%s/%s/ical' % (self.orga.slug, self.event.slug))
        self.assertEqual(ical['Content-Type'], 'text/calendar')
        self.assertEqual(ical['Content-Disposition'], 'attachment; filename="{}-{}-0.ics"'.format(
            self.orga.slug, self.event.slug
        ))

    def test_header_footer(self):
        ical = self.client.get('/%s/%s/ical' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertTrue(ical.startswith('BEGIN:VCALENDAR'), 'missing VCALENDAR header')
        self.assertTrue(ical.strip().endswith('END:VCALENDAR'), 'missing VCALENDAR footer')
        self.assertIn('BEGIN:VEVENT', ical, 'missing VEVENT header')
        self.assertIn('END:VEVENT', ical, 'missing VEVENT footer')

    def test_timezone_header_footer(self):
        self.event.settings.timezone = 'Asia/Tokyo'
        self.event.save()
        ical = self.client.get('/%s/%s/ical' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertTrue(ical.startswith('BEGIN:VCALENDAR'), 'missing VCALENDAR header')
        self.assertTrue(ical.strip().endswith('END:VCALENDAR'), 'missing VCALENDAR footer')
        self.assertIn('BEGIN:VEVENT', ical, 'missing VEVENT header')
        self.assertIn('END:VEVENT', ical, 'missing VEVENT footer')
        self.assertIn('BEGIN:VTIMEZONE', ical, 'missing VTIMEZONE header')
        self.assertIn('END:VTIMEZONE', ical, 'missing VTIMEZONE footer')

    def test_metadata(self):
        ical = self.client.get('/%s/%s/ical' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertIn('VERSION:2.0', ical, 'incorrect version tag - 2.0')
        self.assertIn('-//pretix//%s//' % settings.PRETIX_INSTANCE_NAME, ical, 'incorrect PRODID')

    def test_event_info(self):
        ical = self.client.get('/%s/%s/ical' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertIn('SUMMARY:%s' % self.event.name, ical, 'incorrect correct summary')
        self.assertIn('LOCATION:DUMMY ARENA', ical, 'incorrect location')
        self.assertIn('ORGANIZER:%s' % self.event.organizer.name, ical, 'incorrect organizer')
        self.assertTrue(re.search(r'DTSTAMP:\d{8}T\d{6}Z', ical), 'incorrect timestamp')
        self.assertTrue(re.search(r'UID:\w*-\w*-0-\d{20}', ical), 'missing UID key')

    def test_utc_timezone(self):
        ical = self.client.get('/%s/%s/ical' % (self.orga.slug, self.event.slug)).content.decode()
        # according to icalendar spec, timezone must NOT be shown if it is UTC
        self.assertIn('DTSTART:%s' % self.event.date_from.strftime('%Y%m%dT%H%M%SZ'), ical, 'incorrect start time')
        self.assertIn('DTEND:%s' % self.event.date_to.strftime('%Y%m%dT%H%M%SZ'), ical, 'incorrect end time')

    def test_include_timezone(self):
        self.event.settings.timezone = 'Asia/Tokyo'
        self.event.save()
        ical = self.client.get('/%s/%s/ical' % (self.orga.slug, self.event.slug)).content.decode()
        # according to icalendar spec, timezone must be shown if it is not UTC
        fmt = '%Y%m%dT%H%M%S'
        self.assertIn('DTSTART;TZID=%s:%s' %
                      (self.event.settings.timezone,
                       self.event.date_from.astimezone(timezone(self.event.settings.timezone)).strftime(fmt)),
                      ical, 'incorrect start time')
        self.assertIn('DTEND;TZID=%s:%s' %
                      (self.event.settings.timezone,
                       self.event.date_to.astimezone(timezone(self.event.settings.timezone)).strftime(fmt)),
                      ical, 'incorrect end time')
        self.assertIn('TZID:%s' % self.event.settings.timezone, ical, 'missing VCALENDAR')

    def test_no_time(self):
        self.event.settings.show_times = False
        self.event.save()
        ical = self.client.get('/%s/%s/ical' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertIn('DTSTART;VALUE=DATE:%s' % self.event.date_from.strftime('%Y%m%d'), ical, 'incorrect start date')
        self.assertIn('DTEND;VALUE=DATE:%s' % self.event.date_to.strftime('%Y%m%d'), ical, 'incorrect end date')

    def test_no_date_to(self):
        self.event.settings.timezone = 'Asia/Tokyo'
        self.event.settings.show_date_to = False
        self.event.save()
        ical = self.client.get('/%s/%s/ical' % (self.orga.slug, self.event.slug)).content.decode()
        fmt = '%Y%m%dT%H%M%S'
        self.assertIn('DTSTART;TZID=%s:%s' %
                      (self.event.settings.timezone,
                       self.event.date_from.astimezone(timezone(self.event.settings.timezone)).strftime(fmt)),
                      ical, 'incorrect start time')
        self.assertNotIn('DTEND', ical, 'unexpected end time attribute')

    def test_no_date_to_and_time(self):
        self.event.settings.show_date_to = False
        self.event.settings.show_times = False
        self.event.save()
        ical = self.client.get('/%s/%s/ical' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertIn('DTSTART;VALUE=DATE:%s' % self.event.date_from.strftime('%Y%m%d'), ical, 'incorrect start date')
        self.assertNotIn('DTEND', ical, 'unexpected end time attribute')

    def test_local_date_diff_from_utc(self):
        self.event.date_from = datetime.datetime(2013, 12, 26, 21, 57, 58, tzinfo=datetime.timezone.utc)
        self.event.date_to = self.event.date_from + datetime.timedelta(days=2)
        self.event.settings.timezone = 'Asia/Tokyo'
        self.event.settings.show_times = False
        self.event.save()
        ical = self.client.get('/%s/%s/ical' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertIn('DTSTART;VALUE=DATE:20131227', ical, 'incorrect start date')
        self.assertIn('DTEND;VALUE=DATE:20131229', ical, 'incorrect end date')


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
