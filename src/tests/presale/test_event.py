import datetime
import re
from decimal import Decimal
from json import loads

from django.conf import settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils.timezone import now
from django_scopes import scopes_disabled
from pytz import timezone
from tests.base import SoupTest
from tests.testdummy.signals import FoobarSalesChannel

from pretix.base.models import (
    Event, Item, ItemCategory, ItemVariation, Order, Organizer, Quota, Team,
    User, WaitingListEntry,
)
from pretix.base.models.items import SubEventItem, SubEventItemVariation


class EventTestMixin:
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(now().year + 1, 12, 26, 14, 0, tzinfo=datetime.timezone.utc),
            live=True, sales_channels=['web', 'bar']
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
    def test_link_rewrite(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True,
                                       description="http://example.org [Sample](http://example.net)")
            q.items.add(item)
        html = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug)).rendered_content

        self.assertNotIn('href="http://example.org', html)
        self.assertNotIn('href="http://example.net', html)
        self.assertIn('href="/redirect/?url=http%3A//example.org%3A', html)
        self.assertIn('href="/redirect/?url=http%3A//example.net%3A', html)

    def test_not_active(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=False)
            q.items.add(item)
        html = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug)).rendered_content
        self.assertNotIn("Early-bird", html)
        self.assertNotIn("btn-add-to-cart", html)

    def test_filter_by_url(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True)
            q.items.add(item)
        doc = self.get_doc('/%s/%s/?item=%d' % (self.orga.slug, self.event.slug, item.pk))
        self.assertIn("Early-bird", doc.select("section .product-row")[0].text)
        doc = self.get_doc('/%s/%s/?item=%d' % (self.orga.slug, self.event.slug, item.pk + 1))
        assert not doc.select("section .product-row")

    def test_without_category(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True)
            q.items.add(item)
        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", doc.select("section .product-row")[0].text)
        self.assertEqual(len(doc.select("#btn-add-to-cart")), 1)

    def test_sales_channel(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True,
                                       sales_channels=['bar'])
            q.items.add(item)
        html = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug)).rendered_content
        self.assertNotIn("Early-bird", html)
        html = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug), PRETIX_SALES_CHANNEL=FoobarSalesChannel).rendered_content
        self.assertIn("Early-bird", html)

    def test_timely_available(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True,
                                       available_until=now() + datetime.timedelta(days=2),
                                       available_from=now() - datetime.timedelta(days=2))
        q.items.add(item)
        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", doc.select("body")[0].text)

    def test_no_longer_available(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True,
                                       available_until=now() - datetime.timedelta(days=2))
            q.items.add(item)
        html = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug)).rendered_content
        self.assertNotIn("Early-bird", html)

    def test_not_yet_available(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True,
                                       available_from=now() + datetime.timedelta(days=2))
        q.items.add(item)
        html = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug)).rendered_content
        self.assertNotIn("Early-bird", html)

    def test_hidden_without_voucher(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0, active=True,
                                       hide_without_voucher=True)
        q.items.add(item)
        html = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug)).rendered_content
        self.assertNotIn("Early-bird", html)

    def test_simple_with_category(self):
        with scopes_disabled():
            c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
            q.items.add(item)
        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Entry tickets", doc.select("section:nth-of-type(1) h3")[0].text)
        self.assertIn("Early-bird", doc.select("section:nth-of-type(1) div:nth-of-type(1)")[0].text)

    def test_simple_without_quota(self):
        with scopes_disabled():
            c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
            Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
        resp = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", resp.rendered_content)

    def test_subevents_inactive_unknown(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(name='Foo', date_from=now(), active=False)
        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se1.pk))
        assert resp.status_code == 404
        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se1.pk + 1000))
        assert resp.status_code == 404

    def test_subevent_list_activeness(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            self.event.subevents.create(name='Foo SE1', date_from=now() + datetime.timedelta(days=1), active=True)
            self.event.subevents.create(name='Foo SE2', date_from=now() + datetime.timedelta(days=1), active=False)
        resp = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Foo SE1", resp.rendered_content)
        self.assertNotIn("Foo SE2", resp.rendered_content)

    def test_subevent_list_ordering(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            self.event.subevents.create(name='Epic SE', date_from=now() + datetime.timedelta(days=1), active=True)
            self.event.subevents.create(name='Cool SE', date_from=now() + datetime.timedelta(days=2), active=True)

        self.event.settings.frontpage_subevent_ordering = 'date_ascending'
        content = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug)).rendered_content
        self.assertLess(content.index('Epic SE'), content.index('Cool SE'))

        self.event.settings.frontpage_subevent_ordering = 'date_descending'
        content = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug)).rendered_content
        self.assertLess(content.index('Cool SE'), content.index('Epic SE'))

        self.event.settings.frontpage_subevent_ordering = 'name_ascending'
        content = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug)).rendered_content
        self.assertLess(content.index('Cool SE'), content.index('Epic SE'))

    def test_subevent_calendar(self):
        self.event.settings.event_list_type = 'calendar'
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(name='Foo SE1', date_from=now() + datetime.timedelta(days=64), active=True)
            self.event.subevents.create(name='Foo SE2', date_from=now() + datetime.timedelta(days=32), active=True)
        resp = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Foo SE2", resp.rendered_content)
        self.assertNotIn("Foo SE1", resp.rendered_content)
        resp = self.client.get('/%s/%s/?year=%d&month=%d' % (self.orga.slug, self.event.slug, se1.date_from.year,
                                                             se1.date_from.month))
        self.assertIn("Foo SE1", resp.rendered_content)
        self.assertNotIn("Foo SE2", resp.rendered_content)

    def test_subevent_week_calendar(self):
        self.event.settings.event_list_type = 'week'
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(name='Foo SE1', date_from=now() + datetime.timedelta(days=24),
                                              active=True)
            self.event.subevents.create(name='Foo SE2', date_from=now() + datetime.timedelta(days=12),
                                        active=True)
        resp = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        print(resp.rendered_content)
        self.assertIn("Foo SE2", resp.rendered_content)
        self.assertNotIn("Foo SE1", resp.rendered_content)
        resp = self.client.get('/%s/%s/?year=%d&week=%d' % (self.orga.slug, self.event.slug,
                                                            se1.date_from.isocalendar()[0],
                                                            se1.date_from.isocalendar()[1]))
        self.assertIn("Foo SE1", resp.rendered_content)
        self.assertNotIn("Foo SE2", resp.rendered_content)

    def test_subevents(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            se2 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se1)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=0)
            q.items.add(item)

        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se1.pk))
        self.assertIn("Early-bird", resp.rendered_content)
        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se2.pk))
        self.assertNotIn("Early-bird", resp.rendered_content)

    def test_subevent_disabled(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            se2 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=15)
            q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se1)
            q.items.add(item)
            q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se2)
            q.items.add(item)
            SubEventItem.objects.create(subevent=se1, item=item, price=12, disabled=True)

        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se1.pk))
        self.assertNotIn("Early-bird", resp.rendered_content)
        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se2.pk))
        self.assertIn("Early-bird", resp.rendered_content)

    def test_subevent_prices(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
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
        with scopes_disabled():
            se1 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            se2 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            tr = self.event.tax_rules.get_or_create(rate=Decimal('19.00'))[0]
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=15,
                                       tax_rule=tr)
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

    def test_variations_subevent_disabled(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            se2 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=15)
            v = ItemVariation.objects.create(item=item, value='Blue')
            q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se1)
            q.items.add(item)
            q.variations.add(v)
            q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se2)
            q.items.add(item)
            q.variations.add(v)
            SubEventItemVariation.objects.create(subevent=se1, variation=v, disabled=True)

        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se1.pk))
        self.assertNotIn("Early-bird", resp.rendered_content)
        resp = self.client.get('/%s/%s/%d/' % (self.orga.slug, self.event.slug, se2.pk))
        self.assertIn("Early-bird", resp.rendered_content)

    def test_no_variations_in_quota(self):
        with scopes_disabled():
            c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
            ItemVariation.objects.create(item=item, value='Blue')
            q.items.add(item)
        resp = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", resp.rendered_content)

    def test_one_variation_in_quota(self):
        with scopes_disabled():
            c = ItemCategory.objects.create(event=self.event, name="Entry tickets", position=0)
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', category=c, default_price=0)
            var1 = ItemVariation.objects.create(item=item, value='Red')
            ItemVariation.objects.create(item=item, value='Blue')
            q.items.add(item)
        q.variations.add(var1)
        self._assert_variation_found()

    def test_one_variation_in_unlimited_quota(self):
        with scopes_disabled():
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
        with scopes_disabled():
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
        self.assertIn("Red", doc.select("section:nth-of-type(1) .variation")[0].text)
        self.assertIn("14.00", doc.select("section:nth-of-type(1) .variation")[0].text)
        self.assertIn("Black", doc.select("section:nth-of-type(1) .variation")[1].text)
        self.assertIn("12.00", doc.select("section:nth-of-type(1) .variation")[1].text)

    def test_require_bundling(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=12)
            q.items.add(item)
            q2 = Quota.objects.create(event=self.event, name='Quota', size=2)
            item2 = Item.objects.create(event=self.event, name='Dinner', default_price=12, require_bundling=True)
            q2.items.add(item2)
            item.bundles.create(bundled_item=item2, designated_price=2, count=1)

        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertEqual(1, len(doc.select(".availability-box")))

    def test_hide_sold_out(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Quota', size=0)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=12)
            q.items.add(item)

        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", doc.select("section:nth-of-type(1) div:nth-of-type(1)")[0].text)
        self.assertIn("SOLD OUT", doc.select("section:nth-of-type(1)")[0].text)

        self.event.settings.hide_sold_out = True

        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        html_element = doc.select("article:nth-of-type(1) div:nth-of-type(1)")
        if (html_element):
            self.assertNotIn("Early-bird", html_element[0].text)
        html_element = doc.select("article:nth-of-type(1)")
        if (html_element):
            self.assertNotIn("SOLD OUT", html_element[0].text)

    def test_hidden_if_available(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Early-bird', size=10)
            q2 = Quota.objects.create(event=self.event, name='Late-bird', size=10)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=12)
            item2 = Item.objects.create(event=self.event, name='Late-bird ticket', default_price=12,
                                        hidden_if_available=q)
            q.items.add(item)
            q2.items.add(item2)
        self.event.settings.hide_sold_out = True

        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", doc.select("section:nth-of-type(1)")[0].text)
        self.assertNotIn("SOLD OUT", doc.select("section:nth-of-type(1)")[0].text)
        self.assertNotIn("Late-bird", doc.select("section:nth-of-type(1)")[0].text)

        q.size = 0
        q.save()

        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertNotIn("Early-bird", doc.select("section:nth-of-type(1)")[0].text)
        self.assertNotIn("SOLD OUT", doc.select("section:nth-of-type(1)")[0].text)
        self.assertIn("Late-bird", doc.select("section:nth-of-type(1)")[0].text)

    def test_bundle_sold_out(self):
        with scopes_disabled():
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=12)
            q.items.add(item)
            q2 = Quota.objects.create(event=self.event, name='Quota', size=0)
            item2 = Item.objects.create(event=self.event, name='Dinner', default_price=12, position=10)
            q2.items.add(item2)
            item.bundles.create(bundled_item=item2, designated_price=2, count=1)

        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", doc.select("section:nth-of-type(1) div:nth-of-type(1)")[0].text)
        self.assertIn("SOLD OUT", doc.select("section:nth-of-type(1)")[0].text)

    def test_bundle_mixed_tax_rate(self):
        with scopes_disabled():
            tr19 = self.event.tax_rules.create(rate=Decimal('19.00'))
            tr7 = self.event.tax_rules.create(rate=Decimal('7.00'))
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=12, tax_rule=tr19)
            q.items.add(item)
            q2 = Quota.objects.create(event=self.event, name='Quota', size=0)
            item2 = Item.objects.create(event=self.event, name='Dinner', default_price=12, tax_rule=tr7, position=10)
            q2.items.add(item2)
            item.bundles.create(bundled_item=item2, designated_price=2, count=1)

        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", doc.select("section:nth-of-type(1) div:nth-of-type(1)")[0].text)
        self.assertIn("12.00", doc.select("section:nth-of-type(1) div.price")[0].text)
        self.assertIn("incl. taxes", doc.select("section:nth-of-type(1) div.price")[0].text)

    def test_bundle_mixed_tax_rate_show_net(self):
        with scopes_disabled():
            self.event.settings.display_net_prices = True
            tr19 = self.event.tax_rules.create(rate=Decimal('19.00'))
            tr7 = self.event.tax_rules.create(rate=Decimal('7.00'))
            q = Quota.objects.create(event=self.event, name='Quota', size=2)
            item = Item.objects.create(event=self.event, name='Early-bird ticket', default_price=12, tax_rule=tr19)
            q.items.add(item)
            q2 = Quota.objects.create(event=self.event, name='Quota', size=0)
            item2 = Item.objects.create(event=self.event, name='Dinner', default_price=12, tax_rule=tr7, position=10)
            q2.items.add(item2)
            item.bundles.create(bundled_item=item2, designated_price=2, count=1)

        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertIn("Early-bird", doc.select("section:nth-of-type(1) div:nth-of-type(1)")[0].text)
        self.assertIn("10.27", doc.select("section:nth-of-type(1) div.price")[0].text)
        self.assertIn("plus taxes", doc.select("section:nth-of-type(1) div.price")[0].text)


class VoucherRedeemItemDisplayTest(EventTestMixin, SoupTest):
    @scopes_disabled()
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
        with scopes_disabled():
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
        assert "Early-bird" in html.rendered_content

    def test_hide_wo_voucher_quota_dont_show(self):
        self.v.show_hidden_items = False
        self.v.save()
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
        with scopes_disabled():
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
        with scopes_disabled():
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
        with scopes_disabled():
            var1 = ItemVariation.objects.create(item=self.item, value='Red', default_price=14, position=1)
            var2 = ItemVariation.objects.create(item=self.item, value='Black', position=2)
            self.q.variations.add(var1)
            self.q.variations.add(var2)
        self.q.size = 0
        self.q.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s' % (self.orga.slug, self.event.slug, self.v.code))
        assert "_voucher_item" not in html.rendered_content

    def test_variations_sold_out_blocking(self):
        with scopes_disabled():
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
        with scopes_disabled():
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
        assert "<del>€14.00</del>" in html.rendered_content

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

    def test_subevent_net_prices(self):
        with scopes_disabled():
            self.event.settings.display_net_prices = True
            self.event.has_subevents = True
            self.event.save()
            self.item.tax_rule = self.event.tax_rules.get_or_create(rate=Decimal('19.00'))[0]
            self.item.save()
            se1 = self.event.subevents.create(name='SE1', date_from=now(), active=True)
            q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se1)

            var1 = ItemVariation.objects.create(item=self.item, value='Red', position=1)
            var2 = ItemVariation.objects.create(item=self.item, value='Black', position=2)
            q.items.add(self.item)
            q.variations.add(var1)
            q.variations.add(var2)
            SubEventItemVariation.objects.create(subevent=se1, variation=var1, price=10)

            self.v.quota = q
            self.v.value = Decimal("2.00")
            self.v.price_mode = 'subtract'
            self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s&subevent=%s' % (
            self.orga.slug, self.event.slug, self.v.code, se1.pk
        ))
        assert "SE1" in html.rendered_content
        assert "Early-bird" in html.rendered_content
        assert "8.40" in html.rendered_content
        assert "6.72" in html.rendered_content

    def test_subevent_prices(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name='SE1', date_from=now(), active=True)
            q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se1)

            var1 = ItemVariation.objects.create(item=self.item, value='Red', position=1)
            var2 = ItemVariation.objects.create(item=self.item, value='Black', position=2)
            q.items.add(self.item)
            q.variations.add(var1)
            q.variations.add(var2)
            SubEventItemVariation.objects.create(subevent=se1, variation=var1, price=10)

            self.v.quota = q
            self.v.value = Decimal("2.00")
            self.v.price_mode = 'subtract'
            self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s&subevent=%s' % (
            self.orga.slug, self.event.slug, self.v.code, se1.pk
        ))
        assert "SE1" in html.rendered_content
        assert "Early-bird" in html.rendered_content
        assert "10.00" in html.rendered_content
        assert "8.00" in html.rendered_content
        assert "variation_%d_%d" % (self.item.pk, var1.pk) in html.rendered_content
        assert "variation_%d_%d" % (self.item.pk, var2.pk) in html.rendered_content

    def test_voucher_ignore_other_subevent(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name='SE1', date_from=now(), active=True)
            se2 = self.event.subevents.create(name='SE2', date_from=now(), active=True)
            q = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se1)

            var1 = ItemVariation.objects.create(item=self.item, value='Red', position=1)
            var2 = ItemVariation.objects.create(item=self.item, value='Black', position=2)
            q.items.add(self.item)
            q.variations.add(var1)
            q.variations.add(var2)

        self.v.subevent = se1
        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s&subevent=%s' % (
            self.orga.slug, self.event.slug, self.v.code, se2.pk
        ))
        assert "SE1" in html.rendered_content

    def test_voucher_quota(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name='SE1', date_from=now(), active=True)
            se2 = self.event.subevents.create(name='SE2', date_from=now(), active=True)
            q = Quota.objects.create(event=self.event, name='Quota', size=0, subevent=se1)
            q2 = Quota.objects.create(event=self.event, name='Quota', size=2, subevent=se2)

            var1 = ItemVariation.objects.create(item=self.item, value='Red', position=1)
            var2 = ItemVariation.objects.create(item=self.item, value='Black', position=2)
            q.variations.add(var1)
            q2.variations.add(var1)
            q.variations.add(var2)
            q2.variations.add(var1)

        self.v.save()
        html = self.client.get('/%s/%s/redeem?voucher=%s&subevent=%s' % (
            self.orga.slug, self.event.slug, self.v.code, se1.pk
        ))
        assert "SE1" in html.rendered_content
        assert 'name="variation_%d_%d' % (self.item.pk, var1.pk) not in html.rendered_content
        assert 'name="variation_%d_%d' % (self.item.pk, var2.pk) not in html.rendered_content


class WaitingListTest(EventTestMixin, SoupTest):
    @scopes_disabled()
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
            '/%s/%s/waitinglist/?item=%d' % (self.orga.slug, self.event.slug, self.item.pk + 1)
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
            '/%s/%s/waitinglist/?item=%d' % (self.orga.slug, self.event.slug, self.item.pk)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('waiting list', response.rendered_content)
        response = self.client.post(
            '/%s/%s/waitinglist/?item=%d' % (self.orga.slug, self.event.slug, self.item.pk), {
                'email': 'foo@bar.com'
            }
        )
        self.assertEqual(response.status_code, 302)
        with scopes_disabled():
            wle = WaitingListEntry.objects.get(email='foo@bar.com')
        assert wle.event == self.event
        assert wle.item == self.item
        assert wle.variation is None
        assert wle.voucher is None
        assert wle.locale == 'en'

    def test_subevent_valid(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name="Foo", date_from=now(), active=True)
            se2 = self.event.subevents.create(name="Foobar", date_from=now(), active=True)
            self.q.subevent = se1
            self.q.save()
            q2 = self.event.quotas.create(name="Foobar", size=100, subevent=se2)
            q2.items.add(self.item)
        response = self.client.get(
            '/%s/%s/waitinglist/?item=%d&subevent=%d' % (self.orga.slug, self.event.slug, self.item.pk, se1.pk)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('waiting list', response.rendered_content)
        response = self.client.post(
            '/%s/%s/waitinglist/?item=%d&subevent=%d' % (self.orga.slug, self.event.slug, self.item.pk, se1.pk), {
                'email': 'foo@bar.com'
            }
        )
        self.assertEqual(response.status_code, 302)
        with scopes_disabled():
            wle = WaitingListEntry.objects.get(email='foo@bar.com')
            assert wle.event == self.event
            assert wle.item == self.item
            assert wle.subevent == se1

    def test_invalid_item(self):
        response = self.client.get(
            '/%s/%s/waitinglist/?item=%d' % (self.orga.slug, self.event.slug, self.item.pk + 1)
        )
        self.assertEqual(response.status_code, 302)

    def test_invalid_subevent(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(name="Foo", date_from=now(), active=False)
        response = self.client.get(
            '/%s/%s/waitinglist/?item=%d' % (self.orga.slug, self.event.slug, self.item.pk)
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get(
            '/%s/%s/waitinglist/?item=%d&subevent=%d' % (self.orga.slug, self.event.slug, self.item.pk, se1.pk + 100)
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.get(
            '/%s/%s/waitinglist/?item=%d&subevent=%d' % (self.orga.slug, self.event.slug, self.item.pk, se1.pk)
        )
        self.assertEqual(response.status_code, 404)

    def test_available(self):
        self.q.size = 1
        self.q.save()
        response = self.client.post(
            '/%s/%s/waitinglist/?item=%d' % (self.orga.slug, self.event.slug, self.item.pk), {
                'email': 'foo@bar.com'
            }
        )
        self.assertEqual(response.status_code, 302)
        with scopes_disabled():
            self.assertFalse(WaitingListEntry.objects.filter(email='foo@bar.com').exists())

    def test_subevent_available(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name="Foo", date_from=now(), active=True)
            se2 = self.event.subevents.create(name="Foobar", date_from=now(), active=True)
            self.q.size = 1
            self.q.subevent = se1
            self.q.save()
            q2 = self.event.quotas.create(name="Foobar", size=0, subevent=se2)
            q2.items.add(self.item)
        response = self.client.post(
            '/%s/%s/waitinglist/?item=%d&subevent=%d' % (self.orga.slug, self.event.slug, self.item.pk, se1.pk), {
                'email': 'foo@bar.com'
            }
        )
        self.assertEqual(response.status_code, 302)
        with scopes_disabled():
            self.assertFalse(WaitingListEntry.objects.filter(email='foo@bar.com').exists())


class DeadlineTest(EventTestMixin, TestCase):
    @scopes_disabled()
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

    def test_event_over(self):
        self.event.date_to = now() - datetime.timedelta(days=1)
        self.event.presale_end = None
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

    def test_saleschannel_disabled(self):
        self.event.presale_start = None
        self.event.presale_end = None
        self.event.sales_channels = []
        self.event.save()
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            '/%s/%s/cart/add' % (self.orga.slug, self.event.slug),
            {
                'item_%d' % self.item.id: '1'
            }
        )
        self.assertEqual(response.status_code, 404)

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
        with scopes_disabled():
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
        with scopes_disabled():
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
        with scopes_disabled():
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
        ical = self.client.get('/%s/%s/ical/' % (self.orga.slug, self.event.slug))
        self.assertEqual(ical['Content-Type'], 'text/calendar')
        self.assertEqual(ical['Content-Disposition'], 'attachment; filename="{}-{}-0.ics"'.format(
            self.orga.slug, self.event.slug
        ))

    def test_header_footer(self):
        ical = self.client.get('/%s/%s/ical/' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertTrue(ical.startswith('BEGIN:VCALENDAR'), 'missing VCALENDAR header')
        self.assertTrue(ical.strip().endswith('END:VCALENDAR'), 'missing VCALENDAR footer')
        self.assertIn('BEGIN:VEVENT', ical, 'missing VEVENT header')
        self.assertIn('END:VEVENT', ical, 'missing VEVENT footer')

    def test_timezone_header_footer(self):
        self.event.settings.timezone = 'Asia/Tokyo'
        self.event.save()
        ical = self.client.get('/%s/%s/ical/' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertTrue(ical.startswith('BEGIN:VCALENDAR'), 'missing VCALENDAR header')
        self.assertTrue(ical.strip().endswith('END:VCALENDAR'), 'missing VCALENDAR footer')
        self.assertIn('BEGIN:VEVENT', ical, 'missing VEVENT header')
        self.assertIn('END:VEVENT', ical, 'missing VEVENT footer')
        self.assertIn('BEGIN:VTIMEZONE', ical, 'missing VTIMEZONE header')
        self.assertIn('END:VTIMEZONE', ical, 'missing VTIMEZONE footer')

    def test_metadata(self):
        ical = self.client.get('/%s/%s/ical/' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertIn('VERSION:2.0', ical, 'incorrect version tag - 2.0')
        self.assertIn('-//pretix//%s//' % settings.PRETIX_INSTANCE_NAME, ical, 'incorrect PRODID')

    def test_event_info(self):
        ical = self.client.get('/%s/%s/ical/' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertIn('SUMMARY:%s' % self.event.name, ical, 'incorrect correct summary')
        self.assertIn('LOCATION:DUMMY ARENA', ical, 'incorrect location')
        self.assertTrue(re.search(r'DTSTAMP:\d{8}T\d{6}Z', ical), 'incorrect timestamp')
        self.assertTrue(re.search(r'UID:pretix-\w*-\w*-0@', ical), 'missing UID key')

    def test_utc_timezone(self):
        ical = self.client.get('/%s/%s/ical/' % (self.orga.slug, self.event.slug)).content.decode()
        # according to icalendar spec, timezone must NOT be shown if it is UTC
        self.assertIn('DTSTART:%s' % self.event.date_from.strftime('%Y%m%dT%H%M%SZ'), ical, 'incorrect start time')
        self.assertIn('DTEND:%s' % self.event.date_to.strftime('%Y%m%dT%H%M%SZ'), ical, 'incorrect end time')

    def test_include_timezone(self):
        self.event.settings.timezone = 'Asia/Tokyo'
        self.event.save()
        ical = self.client.get('/%s/%s/ical/' % (self.orga.slug, self.event.slug)).content.decode()
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
        ical = self.client.get('/%s/%s/ical/' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertIn('DTSTART;VALUE=DATE:%s' % self.event.date_from.strftime('%Y%m%d'), ical, 'incorrect start date')
        self.assertIn('DTEND;VALUE=DATE:%s' % (self.event.date_to + datetime.timedelta(days=1)).strftime('%Y%m%d'), ical, 'incorrect end date')

    def test_no_date_to(self):
        self.event.settings.timezone = 'Asia/Tokyo'
        self.event.settings.show_date_to = False
        self.event.save()
        ical = self.client.get('/%s/%s/ical/' % (self.orga.slug, self.event.slug)).content.decode()
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
        ical = self.client.get('/%s/%s/ical/' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertIn('DTSTART;VALUE=DATE:%s' % self.event.date_from.strftime('%Y%m%d'), ical, 'incorrect start date')
        self.assertNotIn('DTEND', ical, 'unexpected end time attribute')

    def test_local_date_diff_from_utc(self):
        self.event.date_from = datetime.datetime(2013, 12, 26, 21, 57, 58, tzinfo=datetime.timezone.utc)
        self.event.date_to = self.event.date_from + datetime.timedelta(days=2)
        self.event.settings.timezone = 'Asia/Tokyo'
        self.event.settings.show_times = False
        self.event.save()
        ical = self.client.get('/%s/%s/ical/' % (self.orga.slug, self.event.slug)).content.decode()
        self.assertIn('DTSTART;VALUE=DATE:20131227', ical, 'incorrect start date')
        self.assertIn('DTEND;VALUE=DATE:20131230', ical, 'incorrect end date')

    def test_subevent_required(self):
        self.event.has_subevents = True
        self.event.save()
        resp = self.client.get('/%s/%s/ical/' % (self.orga.slug, self.event.slug))
        assert resp.status_code == 404
        resp = self.client.get('/%s/%s/ical/100/' % (self.orga.slug, self.event.slug))
        assert resp.status_code == 404

    def test_subevent(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(
                name='My fancy subevent',
                location='Heeeeeere',
                date_from=datetime.datetime(2014, 12, 26, 21, 57, 58, tzinfo=datetime.timezone.utc),
                date_to=datetime.datetime(2014, 12, 28, 21, 57, 58, tzinfo=datetime.timezone.utc),
                active=True
            )
        self.event.settings.show_times = False
        ical = self.client.get('/%s/%s/ical/%d/' % (self.orga.slug, self.event.slug, se1.pk)).content.decode()
        self.assertIn('DTSTART;VALUE=DATE:20141226', ical, 'incorrect start date')
        self.assertIn('DTEND;VALUE=DATE:20141229', ical, 'incorrect end date')
        self.assertIn('SUMMARY:%s' % se1.name, ical, 'incorrect correct summary')
        self.assertIn('LOCATION:Heeeeeere', ical, 'incorrect location')


class EventMicrodataTest(EventTestMixin, SoupTest):
    def setUp(self):
        super().setUp()
        self.event.settings.show_date_to = True
        self.event.settings.show_times = True
        self.event.location = 'DUMMY ARENA'
        self.event.date_from = datetime.datetime(2013, 12, 26, 21, 57, 58, tzinfo=datetime.timezone.utc)
        self.event.date_to = self.event.date_from + datetime.timedelta(days=2)
        self.event.settings.timezone = 'UTC'
        self.event.save()

    def _get_json(self):
        doc = self.get_doc('/%s/%s/' % (self.orga.slug, self.event.slug))
        microdata = loads(doc.find(type="application/ld+json").string)
        return microdata

    def test_name(self):
        md = self._get_json()
        self.assertEqual(self.event.name, md['name'], msg='Name not present')

    def test_location(self):
        md = self._get_json()
        self.assertEqual(self.event.location, md['location']['address'], msg='Location not present')

    def test_date_to(self):
        md = self._get_json()
        self.assertEqual(self.event.date_to.isoformat(), md['endDate'], msg='Date To not present')
        self.event.settings.show_date_to = False
        md = self._get_json()
        self.assertNotIn(self.event.date_to.isoformat(), md,
                         msg='Date To present when show date to setting is false')

    def test_no_times(self):
        self.event.settings.show_times = False
        md = self._get_json()
        self.assertNotEqual(self.event.date_from.isoformat(), md['startDate'], msg='Date including time present')
        self.assertEqual(self.event.date_from.date().isoformat(), md['startDate'], msg='Date not present at all')

    def test_date_from(self):
        md = self._get_json()
        self.assertEqual(self.event.date_from.isoformat(), md['startDate'], msg='Date From not present')


class EventSlugBanlistValidatorTest(EventTestMixin, SoupTest):
    @scopes_disabled()
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


class EventLocaleTest(EventTestMixin, SoupTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.event.settings.locales = ['de', 'en']
        self.event.settings.locale = 'de'
        self.event.settings.timezone = 'UTC'

    def test_german_by_default(self):
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('26. Dezember', response.rendered_content)
        self.assertIn('14:00', response.rendered_content)

    def test_english_no_region_set(self):
        self.client.get('/locale/set?locale=en')
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('Dec. 26,', response.rendered_content)
        self.assertIn('14:00', response.rendered_content)

    def test_english_region_US(self):
        self.event.settings.region = 'US'
        self.client.get('/locale/set?locale=en')
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('Dec. 26,', response.rendered_content)
        self.assertIn('2 p.m.', response.rendered_content)

    def test_german_region_US(self):
        self.event.settings.region = 'US'
        self.client.get('/locale/set?locale=de')
        response = self.client.get(
            '/%s/%s/' % (self.orga.slug, self.event.slug)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('26. Dezember', response.rendered_content)
        self.assertIn('14:00', response.rendered_content)
