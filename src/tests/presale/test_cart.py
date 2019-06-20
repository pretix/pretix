import datetime
import json
from datetime import timedelta
from decimal import Decimal

from bs4 import BeautifulSoup
from django.test import TestCase
from django.utils.timezone import now
from django_countries.fields import Country
from django_scopes import scopes_disabled

from pretix.base.decimal import round_decimal
from pretix.base.models import (
    CartPosition, Event, InvoiceAddress, Item, ItemCategory, ItemVariation,
    Organizer, Question, QuestionAnswer, Quota, SeatingPlan, Voucher,
)
from pretix.base.models.items import (
    ItemAddOn, ItemBundle, SubEventItem, SubEventItemVariation,
)
from pretix.base.services.cart import (
    CartError, CartManager, error_messages, update_tax_rates,
)
from pretix.testutils.scope import classscope
from pretix.testutils.sessions import get_cart_session_key


class CartTestMixin:
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(now().year + 1, 12, 26, tzinfo=datetime.timezone.utc),
            live=True,
            plugins="pretix.plugins.banktransfer"
        )
        self.tr19 = self.event.tax_rules.create(rate=Decimal('19.00'))
        self.category = ItemCategory.objects.create(event=self.event, name="Everything", position=0)
        self.quota_shirts = Quota.objects.create(event=self.event, name='Shirts', size=2)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', category=self.category, default_price=12,
                                         tax_rule=self.tr19)
        self.quota_shirts.items.add(self.shirt)
        self.shirt_red = ItemVariation.objects.create(item=self.shirt, default_price=14, value='Red')
        self.shirt_blue = ItemVariation.objects.create(item=self.shirt, value='Blue')
        self.quota_shirts.variations.add(self.shirt_red)
        self.quota_shirts.variations.add(self.shirt_blue)
        self.quota_tickets = Quota.objects.create(event=self.event, name='Tickets', size=5)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          category=self.category, default_price=23,
                                          tax_rule=self.tr19)
        self.quota_tickets.items.add(self.ticket)

        self.quota_all = Quota.objects.create(event=self.event, name='All', size=None)
        self.quota_all.items.add(self.ticket)
        self.quota_all.items.add(self.shirt)
        self.quota_all.variations.add(self.shirt_blue)
        self.quota_all.variations.add(self.shirt_red)

        self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.session_key = get_cart_session_key(self.client, self.event)


class CartTest(CartTestMixin, TestCase):

    def test_after_presale(self):
        self.event.presale_end = now() - timedelta(days=1)
        self.event.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'alert-danger' in response.rendered_content
        with scopes_disabled():
            assert not CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists()

    def test_after_payment_period(self):
        self.event.settings.payment_term_last = (now() - datetime.timedelta(days=1)).date().isoformat()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'alert-danger' in response.rendered_content
        with scopes_disabled():
            assert not CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists()

    def test_after_event(self):
        self.event.date_to = now() - timedelta(days=1)
        self.event.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'alert-danger' in response.rendered_content
        with scopes_disabled():
            assert not CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists()

    def test_before_presale(self):
        self.event.presale_start = now() + timedelta(days=1)
        self.event.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'alert-danger' in response.rendered_content
        with scopes_disabled():
            assert not CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists()

    def test_simple(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_widget_data_post(self):
        self.event.settings.attendee_names_asked = True
        self.event.settings.attendee_emails_asked = True
        with scopes_disabled():
            q = self.event.questions.create(
                event=self.event, question='What is your shoe size?', type=Question.TYPE_NUMBER,
                required=True
            )
            q.items.add(self.ticket)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'widget_data': json.dumps({
                'attendee-name-full-name': 'John Doe',
                'email': 'foo@example.com',
                'question-' + q.identifier: '43'
            })
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
            self.assertEqual(len(objs), 1)
            self.assertEqual(objs[0].item, self.ticket)
            self.assertIsNone(objs[0].variation)
            self.assertEqual(objs[0].price, 23)
            self.assertEqual(objs[0].attendee_email, "foo@example.com")
            self.assertEqual(objs[0].attendee_name, "John Doe")
            a = objs[0].answers.first()
            self.assertEqual(a.answer, "43")
            self.assertEqual(a.question, q)

    def test_widget_data_ignored_unknown_or_unasked(self):
        self.event.settings.attendee_names_asked = False
        self.event.settings.attendee_emails_asked = False
        with scopes_disabled():
            q = self.event.questions.create(
                event=self.event, question='What is your shoe size?', type=Question.TYPE_NUMBER,
                required=True
            )
            q.items.add(self.ticket)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'widget_data': json.dumps({
                'attendee-name-full-name': 'John Doe',
                'email': 'foo@example.com',
                'question-' + q.identifier: 'bla'
            })
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
            self.assertEqual(len(objs), 1)
            self.assertEqual(objs[0].item, self.ticket)
            self.assertIsNone(objs[0].variation)
            self.assertEqual(objs[0].price, 23)
            assert not objs[0].attendee_email
            assert not objs[0].attendee_name
            assert not objs[0].answers.exists()

    def test_widget_data_session(self):
        self.event.settings.attendee_names_asked = True
        self.event.settings.attendee_emails_asked = True
        with scopes_disabled():
            q = self.event.questions.create(
                event=self.event, question='What is your shoe size?', type=Question.TYPE_NUMBER,
                required=True
            )
            q.items.add(self.ticket)
        self._set_session('widget_data', {
            'attendee-name': 'John Doe',
            'email': 'foo@example.com',
            'question-' + q.identifier: '43'
        })
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
            self.assertEqual(len(objs), 1)
            self.assertEqual(objs[0].item, self.ticket)
            self.assertIsNone(objs[0].variation)
            self.assertEqual(objs[0].price, 23)
            self.assertEqual(objs[0].attendee_email, "foo@example.com")
            self.assertEqual(objs[0].attendee_name, "John Doe")
            a = objs[0].answers.first()
            self.assertEqual(a.answer, "43")
            self.assertEqual(a.question, q)

    def _set_session(self, key, value):
        session = self.client.session
        session['carts'][get_cart_session_key(self.client, self.event)][key] = value
        session.save()

    def _enable_reverse_charge(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        with scopes_disabled():
            ia = InvoiceAddress.objects.create(
                is_business=True, vat_id='ATU1234567', vat_id_validated=True,
                country=Country('AT'),
            )
        self._set_session('invoice_address', ia.pk)
        return ia

    def test_reverse_charge(self):
        self._enable_reverse_charge()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
            self.assertEqual(len(objs), 1)
            self.assertEqual(objs[0].price, round_decimal(Decimal('23.00') / Decimal('1.19')))

    def test_subevent_missing(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            self.quota_tickets.subevent = se
            self.quota_tickets.save()
            q = se.quotas.create(name="foo", size=None, event=self.event)
        q.items.add(self.ticket)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=False)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_voucher_subevent(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            self.quota_tickets.subevent = se
            self.quota_tickets.save()
            v = Voucher.objects.create(item=self.ticket, event=self.event, subevent=se)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
            'subevent': se.pk
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)
        self.assertEqual(objs[0].subevent, se)

    def test_voucher_any_subevent(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, event=self.event)
            self.event.has_subevents = True
            self.event.save()
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            self.quota_tickets.subevent = se
            self.quota_tickets.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
            'subevent': se.pk
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)
        self.assertEqual(objs[0].subevent, se)

    def test_voucher_wrong_subevent(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            se2 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            v = Voucher.objects.create(item=self.ticket, event=self.event, subevent=se2)
            self.quota_tickets.subevent = se
            self.quota_tickets.save()
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
            'subevent': se.pk
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_inactive_subevent(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=False)
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.ticket)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'subevent': se.pk
        }, follow=False)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_subevent_ignore_series_date(self):
        self.event.has_subevents = True
        self.event.date_to = now() - timedelta(days=1)
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True,
                                             presale_end=now() + timedelta(days=1))
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.ticket)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'subevent': se.pk
        }, follow=False)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)

    def test_subevent_payment_period_over(self):
        self.event.has_subevents = True
        self.event.save()
        self.event.settings.payment_term_last = 'RELDATE/1/23:59:59/date_from/'
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.ticket)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'subevent': se.pk
        }, follow=False)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_subevent_sale_over(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True,
                                             presale_end=now() - timedelta(days=1))
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.ticket)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'subevent': se.pk
        }, follow=False)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_subevent_sale_not_yet(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True,
                                             presale_start=now() + timedelta(days=1))
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.ticket)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'subevent': se.pk
        }, follow=False)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_simple_subevent(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.ticket)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'subevent': se.pk
        }, follow=False)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)
        self.assertEqual(objs[0].subevent, se)

    def test_subevent_sold_out(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            self.event.subevents.create(name='Foo', date_from=now(), active=True)
            q = se1.quotas.create(name="foo", size=0, event=self.event)
            q.items.add(self.ticket)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'subevent': se1.pk
        }, follow=False)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_other_subevent_sold_out(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            se2 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            q = se1.quotas.create(name="foo", size=0, event=self.event)
            q.items.add(self.ticket)
            q = se2.quotas.create(name="foo", size=100, event=self.event)
            q.items.add(self.ticket)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'subevent': se2.pk
        }, follow=False)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)

    def test_subevent_no_quota(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            se2 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            q = se1.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.ticket)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'subevent': se2.pk
        }, follow=False)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_subevent_price(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.ticket)
            SubEventItem.objects.create(subevent=se, item=self.ticket, price=42)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'subevent': se.pk
        }, follow=False)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 42)
        self.assertEqual(objs[0].subevent, se)

    def test_free_price(self):
        self.ticket.free_price = True
        self.ticket.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'price_%d' % self.ticket.id: '24.00'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('24', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('24', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 24)

    def test_free_price_only_if_allowed(self):
        self.ticket.free_price = False
        self.ticket.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'price_%d' % self.ticket.id: '24.00'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_free_price_lower_bound(self):
        self.ticket.free_price = False
        self.ticket.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'price_%d' % self.ticket.id: '12.00'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_variation_inactive(self):
        self.shirt_red.active = False
        self.shirt_red.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_variation(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Shirt', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('Red', doc.select('.cart .cart-row')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('14', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('14', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)
        self.assertEqual(objs[0].price, 14)

    def test_variation_free_price(self):
        self.shirt.free_price = True
        self.shirt.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            'price_%d_%d' % (self.shirt.id, self.shirt_red.id): '16',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Shirt', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('Red', doc.select('.cart .cart-row')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('16', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('16', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)
        self.assertEqual(objs[0].price, 16)

    def test_subevent_variation_price(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.variations.add(self.shirt_red)
            SubEventItemVariation.objects.create(subevent=se, variation=self.shirt_red, price=42)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            'subevent': se.pk
        }, follow=False)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)
        self.assertEqual(objs[0].price, 42)
        self.assertEqual(objs[0].subevent, se)

    def test_count(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('2', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('46', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 2)
        for obj in objs:
            self.assertEqual(obj.item, self.ticket)
            self.assertIsNone(obj.variation)
            self.assertEqual(obj.price, 23)

    def test_multiple(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2',
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart')[0].text)
        self.assertIn('Shirt', doc.select('.cart')[0].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 3)
        self.assertIn(self.shirt, [obj.item for obj in objs])
        self.assertIn(self.shirt_red, [obj.variation for obj in objs])
        self.assertIn(self.ticket, [obj.item for obj in objs])

    def test_fuzzy_input(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: 'a',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('numbers only', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '-2',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('numbers only', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_blue.id): 'a',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('numbers only', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_a_%d' % (self.shirt_blue.id): '-2',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('numbers only', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('did not select any products', doc.select('.alert-warning')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_wrong_event(self):
        event2 = Event.objects.create(
            organizer=self.orga, name='MRMCD', slug='mrmcd',
            date_from=datetime.datetime(2014, 9, 6, tzinfo=datetime.timezone.utc)
        )
        shirt2 = Item.objects.create(event=event2, name='T-Shirt', default_price=12)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % shirt2.id: '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('not available', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_no_quota(self):
        shirt2 = Item.objects.create(event=self.event, name='T-Shirt', default_price=12)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % shirt2.id: '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_wrong_sales_channel(self):
        self.ticket.sales_channels = ['bar']
        self.ticket.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 0)

    def test_other_sales_channel(self):
        self.ticket.sales_channels = ['bar']
        self.ticket.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True, PRETIX_SALES_CHANNEL='bar')
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 1)

    def test_in_time_available(self):
        self.ticket.available_until = now() + timedelta(days=2)
        self.ticket.available_from = now() - timedelta(days=2)
        self.ticket.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 1)

    def test_no_longer_available(self):
        self.ticket.available_until = now() - timedelta(days=2)
        self.ticket.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 0)

    def test_not_yet_available(self):
        self.ticket.available_from = now() + timedelta(days=2)
        self.ticket.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 0)

    def test_max_items(self):
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        self.event.settings.max_items_per_order = 5
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '5',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('more than', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 1)

    def test_max_per_item_failed(self):
        self.ticket.max_per_order = 2
        self.ticket.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('more than', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 1)

    def test_max_per_item_success(self):
        self.ticket.max_per_order = 3
        self.ticket.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 3)

    def test_min_per_item_failed(self):
        self.quota_tickets.size = 30
        self.quota_tickets.save()
        self.event.settings.max_items_per_order = 20
        self.ticket.min_per_order = 10
        self.ticket.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '4',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('at least', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 0)

    def test_min_per_item_success(self):
        self.quota_tickets.size = 30
        self.quota_tickets.save()
        self.event.settings.max_items_per_order = 20
        self.ticket.min_per_order = 10
        self.ticket.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '10',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 10)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '3',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 13)

    def test_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_quota_partly(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_subevent_quota_partly(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            self.quota_tickets.size = 1
            self.quota_tickets.subevent = se
            self.quota_tickets.save()
            q2 = self.event.quotas.create(name='Foo', size=15)
            q2.items.add(self.ticket)

        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2',
            'subevent': se.pk
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_renew_in_time(self):
        with scopes_disabled():
            cp = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1'
        }, follow=True)
        cp.refresh_from_db()
        self.assertGreater(cp.expires, now() + timedelta(minutes=10))

    def test_renew_expired_successfully(self):
        with scopes_disabled():
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1'
        }, follow=True)
        with scopes_disabled():
            obj = CartPosition.objects.get(id=cp1.id)
        self.assertEqual(obj.item, self.ticket)
        self.assertIsNone(obj.variation)
        self.assertEqual(obj.price, 23)
        self.assertGreater(obj.expires, now())

    def test_renew_questions(self):
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
            q1 = Question.objects.create(
                event=self.event, question='Age', type=Question.TYPE_NUMBER,
                required=True
            )
            self.ticket.questions.add(q1)
            cr1.answers.add(QuestionAnswer.objects.create(
                cartposition=cr1, question=q1, answer='23'
            ))
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        with scopes_disabled():
            obj = CartPosition.objects.get(id=cr1.id)
            self.assertEqual(obj.answers.get(question=q1).answer, '23')

    def test_renew_expired_failed(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cp1.id).exists())

    def test_subevent_renew_expired_successfully(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            self.quota_tickets.subevent = se
            self.quota_tickets.save()
            self.quota_shirts.subevent = se
            self.quota_shirts.save()
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), subevent=se
            )
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            'subevent': se.pk,
        }, follow=True)
        with scopes_disabled():
            obj = CartPosition.objects.get(id=cp1.id)
        self.assertEqual(obj.item, self.ticket)
        self.assertIsNone(obj.variation)
        self.assertEqual(obj.price, 23)
        self.assertEqual(obj.subevent, se)
        self.assertGreater(obj.expires, now())

    def test_subevent_renew_expired_failed(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
            self.quota_tickets.subevent = se
            self.quota_tickets.size = 0
            self.quota_tickets.save()
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), subevent=se
            )
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'subevent': se.pk,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cp1.id).exists())

    def test_remove_simple(self):
        with scopes_disabled():
            cp = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'id': cp.pk
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('empty', doc.select('.alert-success')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_remove_min(self):
        self.ticket.min_per_order = 2
        self.ticket.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
            cp = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'id': cp.pk
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('less than', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_remove_variation(self):
        with scopes_disabled():
            cp = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.shirt, variation=self.shirt_red,
                price=14, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'id': cp.pk
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('empty', doc.select('.alert-success')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_remove_invalid(self):
        with scopes_disabled():
            cp = CartPosition.objects.create(
                event=self.event, cart_id='invalid', item=self.shirt, variation=self.shirt_red,
                price=14, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'id': cp.pk
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert doc.select('.alert-danger')

    def test_remove_one_of_multiple(self):
        with scopes_disabled():
            cp = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'id': cp.pk
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('updated', doc.select('.alert-success')[0].text)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 1)

    def test_remove_all(self):
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.shirt, variation=self.shirt_red,
                price=14, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/cart/clear' % (self.orga.slug, self.event.slug), {}, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('empty', doc.select('.alert-success')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_remove_expired_voucher(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, event=self.event, valid_until=now() - timedelta(days=1))
            cp = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), voucher=v
            )
        self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'id': cp.pk
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_voucher(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_voucher_expired_readd(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, event=self.event, block_quota=True)
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), voucher=v
            )
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
        }, follow=True)
        cp1.refresh_from_db()
        with scopes_disabled():
            self.assertGreater(cp1.expires, now())
        assert cp1.voucher == v

    def test_voucher_variation(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.shirt, variation=self.shirt_red, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)

    def test_voucher_quota(self):
        with scopes_disabled():
            v = Voucher.objects.create(quota=self.quota_shirts, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)

    def test_voucher_quota_invalid_item(self):
        with scopes_disabled():
            v = Voucher.objects.create(quota=self.quota_tickets, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_voucher_item_invalid_item(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.shirt, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'itme_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_voucher_item_invalid_variation(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.shirt, variation=self.shirt_blue, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_voucher_item_not_available_error(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, event=self.event)
        self.ticket.available_until = now() - timedelta(days=2)
        self.ticket.save()
        response = self.client.get('/%s/%s/redeem' % (self.orga.slug, self.event.slug),
                                   {'voucher': v.code},
                                   follow=True)
        assert error_messages['voucher_item_not_available'] in response.rendered_content

    def test_voucher_price(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set')
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('12.00'))

    def test_voucher_price_negative(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('1337.00'), event=self.event, price_mode='subtract')
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('0.00'))

    def test_voucher_price_percent(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('10.00'), price_mode='percent', event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('20.70'))

    def test_voucher_price_subtract(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('10.00'), price_mode='subtract', event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('13.00'))

    def test_voucher_free_price(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('10.00'), price_mode='percent', event=self.event)
        self.ticket.free_price = True
        self.ticket.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'price_%d' % self.ticket.id: '21.00',
            '_voucher_code': v.code,
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('21', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('21', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('21.00'))

    def test_voucher_free_price_lower_bound(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('10.00'), price_mode='percent', event=self.event)
        self.ticket.free_price = False
        self.ticket.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'price_%d' % self.ticket.id: '20.00',
            '_voucher_code': v.code,
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('20.70', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('20.70', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('20.70'))

    def test_voucher_redemed(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, redeemed=1)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('already been used', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_voucher_expired(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                       valid_until=now() - timedelta(days=2))
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('expired', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_voucher_invalid(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': 'ASDFGH',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('not known', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_voucher_quota_empty(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_voucher_quota_ignore(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                       allow_ignore_quota=True, price_mode='set')
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('12.00'))

    def test_voucher_quota_block(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                       block_quota=True, price_mode='set')
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('12.00'))

    def test_voucher_doubled(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set')
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('12.00'))

        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('currently locked', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            self.assertEqual(1, CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count())

    def test_require_voucher(self):
        with scopes_disabled():
            v = Voucher.objects.create(quota=self.quota_shirts, event=self.event)
        self.shirt.require_voucher = True
        self.shirt.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            '_voucher_code': v.code
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)

    def test_require_voucher_failed(self):
        self.shirt.require_voucher = True
        self.shirt.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_voucher_quota_other_quota_full(self):
        with scopes_disabled():
            quota2 = self.event.quotas.create(name='Test', size=0)
            quota2.variations.add(self.shirt_red)
            v = Voucher.objects.create(quota=self.quota_shirts, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            '_voucher_code': v.code
        }, follow=True)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 0)

    def test_hide_without_voucher(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.shirt, event=self.event)
        self.shirt.hide_without_voucher = True
        self.shirt.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            '_voucher_code': v.code
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)

    def test_hide_without_voucher_failed(self):
        self.shirt.hide_without_voucher = True
        self.shirt.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_voucher_multiuse_ok(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                       max_usages=2, redeemed=0)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            positions = CartPosition.objects.filter(cart_id=self.session_key, event=self.event)
            assert positions.exists()
            assert all(cp.voucher == v for cp in positions)

    def test_voucher_multiuse_multiprod_ok(self):
        with scopes_disabled():
            v = Voucher.objects.create(quota=self.quota_all, value=Decimal('12.00'), event=self.event,
                                       max_usages=2, redeemed=0)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            positions = CartPosition.objects.filter(cart_id=self.session_key, event=self.event)
            assert positions.exists()
            assert all(cp.voucher == v for cp in positions)

    def test_voucher_multiuse_partially(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                       max_usages=2, redeemed=1)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2',
            '_voucher_code': v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('only be redeemed 1 more time', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            positions = CartPosition.objects.filter(cart_id=self.session_key, event=self.event)
            assert positions.count() == 1

    def test_voucher_multiuse_multiprod_partially(self):
        with scopes_disabled():
            v = Voucher.objects.create(quota=self.quota_all, value=Decimal('12.00'), event=self.event,
                                       max_usages=2, redeemed=1)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            '_voucher_code': v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('already been used', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            positions = CartPosition.objects.filter(cart_id=self.session_key, event=self.event)
            assert positions.count() == 1
            assert all(cp.voucher == v for cp in positions)

    def test_voucher_multiuse_redeemed(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                       max_usages=2, redeemed=2)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2',
            '_voucher_code': v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('already been used', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            positions = CartPosition.objects.filter(cart_id=self.session_key, event=self.event)
            assert not positions.exists()

    def test_voucher_multiuse_multiprod_redeemed(self):
        with scopes_disabled():
            v = Voucher.objects.create(quota=self.quota_all, value=Decimal('12.00'), event=self.event,
                                       max_usages=2, redeemed=2)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            '_voucher_code': v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('already been used', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            positions = CartPosition.objects.filter(cart_id=self.session_key, event=self.event)
            assert not positions.exists()

    def test_voucher_multiuse_redeemed_in_my_cart(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                       max_usages=2, redeemed=1)
            CartPosition.objects.create(
                expires=now() - timedelta(minutes=10), item=self.ticket, voucher=v, price=Decimal('12.00'),
                event=self.event, cart_id=self.session_key
            )
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('already been used', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            positions = CartPosition.objects.filter(cart_id=self.session_key, event=self.event)
            assert positions.count() == 1

    def test_voucher_multiuse_redeemed_in_other_cart(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                       max_usages=2, redeemed=1)
            CartPosition.objects.create(
                expires=now() + timedelta(minutes=10), item=self.ticket, voucher=v, price=Decimal('12.00'),
                event=self.event, cart_id='other'
            )
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('currently locked', doc.select('.alert-danger')[0].text)
        with scopes_disabled():
            positions = CartPosition.objects.filter(cart_id=self.session_key, event=self.event)
            assert not positions.exists()

    def test_voucher_multiuse_redeemed_in_other_expired_cart(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                       max_usages=2, redeemed=1)
            CartPosition.objects.create(
                expires=now() - timedelta(minutes=10), item=self.ticket, voucher=v, price=Decimal('12.00'),
                event=self.event, cart_id='other'
            )
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code,
        }, follow=True)
        with scopes_disabled():
            positions = CartPosition.objects.filter(cart_id=self.session_key, event=self.event)
            assert positions.count() == 1


class CartAddonTest(CartTestMixin, TestCase):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.workshopcat = ItemCategory.objects.create(name="Workshops", is_addon=True, event=self.event)
        self.workshopquota = Quota.objects.create(event=self.event, name='Workshop 1', size=5)
        self.workshop1 = Item.objects.create(event=self.event, name='Workshop 1',
                                             category=self.workshopcat, default_price=12)
        self.workshop2 = Item.objects.create(event=self.event, name='Workshop 2',
                                             category=self.workshopcat, default_price=12)
        self.workshop3 = Item.objects.create(event=self.event, name='Workshop 3',
                                             category=self.workshopcat, default_price=12)
        self.workshop3a = ItemVariation.objects.create(item=self.workshop3, value='3a')
        self.workshop3b = ItemVariation.objects.create(item=self.workshop3, value='3b')
        self.workshopquota.items.add(self.workshop1)
        self.workshopquota.items.add(self.workshop2)
        self.workshopquota.items.add(self.workshop3)
        self.workshopquota.variations.add(self.workshop3a)
        self.workshopquota.variations.add(self.workshop3b)
        self.addon1 = ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat)
        self.cm = CartManager(event=self.event, cart_id=self.session_key)

    @classscope(attr='orga')
    def test_cart_set_simple_addon_included(self):
        self.addon1.price_included = True
        self.addon1.save()
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )

        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop1.pk,
                'variation': None
            }
        ])
        self.cm.commit()
        cp2 = cp1.addons.first()
        assert cp2.item == self.workshop1
        assert cp2.price == 0

    @classscope(attr='orga')
    def test_cart_addon_remove_parent(self):
        self.addon1.price_included = True
        self.addon1.save()
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )

        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop1.pk,
                'variation': None
            }
        ])
        self.cm.commit()
        cp2 = cp1.addons.first()
        assert cp2.price == 0

        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'id': cp1.pk
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('empty', doc.select('.alert-success')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    @classscope(attr='orga')
    def test_cart_set_simple_addon(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )

        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop1.pk,
                'variation': None
            }
        ])
        self.cm.commit()
        cp2 = cp1.addons.first()
        assert cp2.item == self.workshop1
        assert cp2.price == 12

    @classscope(attr='orga')
    def test_cart_subevent_set_simple_addon(self):
        self.event.has_subevents = True
        self.event.save()
        se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
        self.workshopquota.subevent = se
        self.workshopquota.save()
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key, subevent=se
        )

        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop1.pk,
                'variation': None
            }
        ])
        self.cm.commit()
        cp2 = cp1.addons.first()
        assert cp2.item == self.workshop1
        assert cp2.subevent == se
        assert cp2.price == 12

    @classscope(attr='orga')
    def test_cart_subevent_set_addon_for_wrong_subevent(self):
        self.event.has_subevents = True
        self.event.save()
        se = self.event.subevents.create(name='Foo', date_from=now(), active=True)
        se2 = self.event.subevents.create(name='Foo', date_from=now(), active=True)
        self.workshopquota.subevent = se2
        self.workshopquota.save()
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key, subevent=se
        )

        with self.assertRaises(CartError):
            self.cm.set_addons([
                {
                    'addon_to': cp1.pk,
                    'item': self.workshop1.pk,
                    'variation': None
                }
            ])

    @classscope(attr='orga')
    def test_wrong_category(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        self.workshop1.category = self.category
        self.workshop1.save()
        with self.assertRaises(CartError):
            self.cm.set_addons([
                {
                    'addon_to': cp1.pk,
                    'item': self.workshop1.pk,
                    'variation': None
                }
            ])

    @classscope(attr='orga')
    def test_invalid_parent(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id='other'
        )
        with self.assertRaises(CartError):
            self.cm.set_addons([
                {
                    'addon_to': cp1.pk,
                    'item': self.workshop1.pk,
                    'variation': None
                }
            ])

    @classscope(attr='orga')
    def test_no_quota_for_addon(self):
        self.workshopquota.delete()
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        with self.assertRaises(CartError):
            self.cm.set_addons([
                {
                    'addon_to': cp1.pk,
                    'item': self.workshop1.pk,
                    'variation': None
                }
            ])

    @classscope(attr='orga')
    def test_unknown_addon_item(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        with self.assertRaises(CartError):
            self.cm.set_addons([
                {
                    'addon_to': cp1.pk,
                    'item': 99999,
                    'variation': None
                }
            ])

    @classscope(attr='orga')
    def test_duplicate_items_for_other_cp(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        cp2 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop1.pk,
                'variation': None
            }
        ])
        self.cm.set_addons([
            {
                'addon_to': cp2.pk,
                'item': self.workshop1.pk,
                'variation': None
            }
        ])
        self.cm.commit()

    @classscope(attr='orga')
    def test_no_duplicate_items_for_same_cp(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        self.addon1.max_count = 2
        self.addon1.save()
        with self.assertRaises(CartError):
            self.cm.set_addons([
                {
                    'addon_to': cp1.pk,
                    'item': self.workshop1.pk,
                    'variation': None
                },
                {
                    'addon_to': cp1.pk,
                    'item': self.workshop1.pk,
                    'variation': None
                }
            ])
        with self.assertRaises(CartError):
            self.cm.set_addons([
                {
                    'addon_to': cp1.pk,
                    'item': self.workshop3.pk,
                    'variation': self.workshop3a.pk
                },
                {
                    'addon_to': cp1.pk,
                    'item': self.workshop3.pk,
                    'variation': self.workshop3b.pk
                }
            ])

    @classscope(attr='orga')
    def test_addon_max_count(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        with self.assertRaises(CartError):
            self.cm.set_addons([
                {
                    'addon_to': cp1.pk,
                    'item': self.workshop1.pk,
                    'variation': None
                },
                {
                    'addon_to': cp1.pk,
                    'item': self.workshop2.pk,
                    'variation': None
                }
            ])

        self.addon1.max_count = 2
        self.addon1.save()
        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop1.pk,
                'variation': None
            },
            {
                'addon_to': cp1.pk,
                'item': self.workshop2.pk,
                'variation': None
            }
        ])

    @classscope(attr='orga')
    def test_addon_min_count(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        self.addon1.min_count = 2
        self.addon1.max_count = 9
        self.addon1.save()
        with self.assertRaises(CartError):
            self.cm.set_addons([
                {
                    'addon_to': cp1.pk,
                    'item': self.workshop2.pk,
                    'variation': None
                }
            ])

        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop1.pk,
                'variation': None
            },
            {
                'addon_to': cp1.pk,
                'item': self.workshop2.pk,
                'variation': None
            }
        ])

    @classscope(attr='orga')
    def test_remove_with_addons(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        cp2 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.workshop1, price=Decimal('12.00'),
            event=self.event, cart_id=self.session_key, addon_to=cp1
        )
        self.cm.remove_item(cp1.pk)
        self.cm.commit()
        assert not CartPosition.objects.filter(pk=cp1.pk).exists()
        assert not CartPosition.objects.filter(pk=cp2.pk).exists()

    @classscope(attr='orga')
    def test_remove_addons(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        cp2 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.workshop1, price=Decimal('12.00'),
            event=self.event, cart_id=self.session_key, addon_to=cp1
        )
        self.cm.set_addons([])
        self.cm.commit()
        assert not CartPosition.objects.filter(pk=cp2.pk).exists()

    @classscope(attr='orga')
    def test_remove_addons_below_min(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        cp2 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.workshop1, price=Decimal('12.00'),
            event=self.event, cart_id=self.session_key, addon_to=cp1
        )
        self.addon1.min_count = 1
        self.addon1.save()
        with self.assertRaises(CartError):
            self.cm.set_addons([])
            self.cm.commit()
        assert CartPosition.objects.filter(pk=cp2.pk).exists()

    @classscope(attr='orga')
    def test_change_product(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.workshop1, price=Decimal('12.00'),
            event=self.event, cart_id=self.session_key, addon_to=cp1
        )
        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop2.pk,
                'variation': None
            }
        ])
        self.cm.commit()
        cp1.refresh_from_db()
        assert cp1.addons.count() == 1
        assert cp1.addons.first().item == self.workshop2

    @classscope(attr='orga')
    def test_unchanged(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.workshop1, price=Decimal('12.00'),
            event=self.event, cart_id=self.session_key, addon_to=cp1
        )
        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop1.pk,
                'variation': None
            }
        ])
        assert not self.cm._operations

    @classscope(attr='orga')
    def test_exceed_max(self):
        self.event.settings.max_items_per_order = 1
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop1.pk,
                'variation': None
            }
        ])
        self.cm.commit()

    @classscope(attr='orga')
    def test_sold_out(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        self.workshopquota.size = 0
        self.workshopquota.save()
        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop1.pk,
                'variation': None
            }
        ])
        with self.assertRaises(CartError):
            self.cm.commit()

    @classscope(attr='orga')
    def test_sold_out_unchanged(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.workshop1, price=Decimal('12.00'),
            event=self.event, cart_id=self.session_key, addon_to=cp1
        )
        self.workshopquota.size = 0
        self.workshopquota.save()
        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop1.pk,
                'variation': None
            }
        ])
        self.cm.commit()

    @classscope(attr='orga')
    def test_sold_out_swap_addons(self):
        cp1 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.workshop1, price=Decimal('12.00'),
            event=self.event, cart_id=self.session_key, addon_to=cp1
        )
        cp2 = CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        CartPosition.objects.create(
            expires=now() + timedelta(minutes=10), item=self.workshop2, price=Decimal('12.00'),
            event=self.event, cart_id=self.session_key, addon_to=cp2
        )
        self.workshopquota.size = 0
        self.workshopquota.save()
        self.cm.set_addons([
            {
                'addon_to': cp1.pk,
                'item': self.workshop2.pk,
                'variation': None
            },
            {
                'addon_to': cp2.pk,
                'item': self.workshop1.pk,
                'variation': None
            },
        ])
        self.cm.commit()
        assert cp1.addons.count() == 1
        assert cp2.addons.count() == 1
        assert cp1.addons.first().item == self.workshop2
        assert cp2.addons.first().item == self.workshop1

    @classscope(attr='orga')
    def test_expand_expired(self):
        cp1 = CartPosition.objects.create(
            expires=now() - timedelta(minutes=10), item=self.ticket, price=Decimal('23.00'),
            event=self.event, cart_id=self.session_key
        )
        cp2 = CartPosition.objects.create(
            expires=now() - timedelta(minutes=10), item=self.workshop1, price=Decimal('12.00'),
            event=self.event, cart_id=self.session_key, addon_to=cp1
        )
        self.cm.extend_expired_positions()
        self.cm.commit()
        cp1.refresh_from_db()
        cp2.refresh_from_db()
        assert cp1.expires > now()
        assert cp2.expires > now()
        assert cp2.addon_to_id == cp1.pk


class CartBundleTest(CartTestMixin, TestCase):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.trans = Item.objects.create(event=self.event, name='Public Transport Ticket',
                                         default_price=2.50, require_bundling=True)
        self.transquota = Quota.objects.create(event=self.event, name='Transport', size=5)
        self.transquota.items.add(self.trans)
        self.bundle1 = ItemBundle.objects.create(
            base_item=self.ticket,
            bundled_item=self.trans,
            designated_price=1.5,
            count=1
        )
        self.cm = CartManager(event=self.event, cart_id=self.session_key)

    @classscope(attr='orga')
    def test_simple_bundle(self):
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1
            }
        ])
        self.cm.commit()
        cp = CartPosition.objects.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 23 - 1.5
        assert cp.addons.count() == 1
        a = cp.addons.get()
        assert a.item == self.trans
        assert a.price == 1.5

    @classscope(attr='orga')
    def test_voucher_on_base_product(self):
        v = self.event.vouchers.create(code="foo", item=self.ticket)
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'voucher': v.code,
                'count': 1
            }
        ])
        self.cm.commit()
        cp = CartPosition.objects.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 23 - 1.5
        assert cp.addons.count() == 1
        assert cp.voucher == v
        a = cp.addons.get()
        assert a.item == self.trans
        assert a.price == 1.5
        assert not a.voucher

    @classscope(attr='orga')
    def test_simple_bundle_with_variation(self):
        v = self.trans.variations.create(value="foo", default_price=4)
        self.transquota.variations.add(v)
        self.bundle1.bundled_variation = v
        self.bundle1.save()
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1
            }
        ])
        self.cm.commit()
        cp = CartPosition.objects.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 23 - 1.5
        assert cp.addons.count() == 1
        a = cp.addons.get()
        assert a.item == self.trans
        assert a.variation == v
        assert a.price == 1.5

    @classscope(attr='orga')
    def test_multiple_bundles(self):
        ItemBundle.objects.create(
            base_item=self.ticket, bundled_item=self.trans, designated_price=1.5, count=1
        )
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1
            }
        ])
        self.cm.commit()
        cp = CartPosition.objects.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 23 - 1.5 - 1.5
        assert cp.addons.count() == 2
        a = cp.addons.first()
        assert a.item == self.trans
        assert a.price == 1.5
        a = cp.addons.last()
        assert a.item == self.trans
        assert a.price == 1.5

    @classscope(attr='orga')
    def test_bundle_with_count(self):
        self.bundle1.count = 2
        self.bundle1.save()
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1
            }
        ])
        self.cm.commit()
        cp = CartPosition.objects.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 23 - 1.5 - 1.5
        assert cp.addons.count() == 2
        a = cp.addons.first()
        assert a.item == self.trans
        assert a.price == 1.5
        a = cp.addons.last()
        assert a.item == self.trans
        assert a.price == 1.5

    @classscope(attr='orga')
    def test_bundle_position_multiple(self):
        self.bundle1.count = 2
        self.bundle1.save()
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 2
            }
        ])
        self.cm.commit()
        assert CartPosition.objects.filter(addon_to__isnull=True).count() == 2
        assert CartPosition.objects.count() == 6
        cp = CartPosition.objects.filter(addon_to__isnull=True).first()
        assert cp.item == self.ticket
        assert cp.price == 23 - 1.5 - 1.5
        assert cp.addons.count() == 2
        a = cp.addons.first()
        assert a.item == self.trans
        assert a.price == 1.5

    @classscope(attr='orga')
    def test_bundle_position_free_price(self):
        self.ticket.free_price = True
        self.ticket.default_price = 1
        self.ticket.save()
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1,
                'price': 20
            }
        ])
        self.cm.commit()
        cp = CartPosition.objects.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 20 - 1.5
        a = cp.addons.get()
        assert a.item == self.trans
        assert a.price == 1.5

    @classscope(attr='orga')
    def test_bundle_position_free_price_lower_than_designated_price(self):
        self.ticket.free_price = True
        self.ticket.default_price = 1
        self.ticket.save()
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1,
                'price': 1.2
            }
        ])
        self.cm.commit()
        cp = CartPosition.objects.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == Decimal('0.00')
        a = cp.addons.get()
        assert a.item == self.trans
        assert a.price == Decimal('1.50')

    @classscope(attr='orga')
    def test_bundle_position_without_designated_price(self):
        self.bundle1.designated_price = 0
        self.bundle1.save()
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1,
            }
        ])
        self.cm.commit()
        cp = CartPosition.objects.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 23
        a = cp.addons.get()
        assert a.item == self.trans
        assert a.price == 0

    @classscope(attr='orga')
    def test_bundle_sold_out(self):
        self.transquota.size = 0
        self.transquota.save()
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1,
            }
        ])
        with self.assertRaises(CartError):
            self.cm.commit()
        assert not CartPosition.objects.exists()

    @classscope(attr='orga')
    def test_bundle_sold_partial_in_bundle(self):
        self.bundle1.count = 2
        self.bundle1.save()
        self.transquota.size = 1
        self.transquota.save()
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1,
            }
        ])
        with self.assertRaises(CartError):
            self.cm.commit()
        assert not CartPosition.objects.exists()

    @classscope(attr='orga')
    def test_bundle_sold_partial_in_bundle_multiple_positions(self):
        self.bundle1.count = 2
        self.bundle1.save()
        self.transquota.size = 3
        self.transquota.save()
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 2,
            }
        ])
        with self.assertRaises(CartError):
            self.cm.commit()
        assert CartPosition.objects.filter(addon_to__isnull=True).count() == 1
        assert CartPosition.objects.filter(addon_to__isnull=False).count() == 2

    @classscope(attr='orga')
    def test_multiple_bundles_sold_out_partially(self):
        ItemBundle.objects.create(
            base_item=self.ticket, bundled_item=self.trans, designated_price=1.5, count=1
        )
        self.transquota.size = 1
        self.transquota.save()
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1
            }
        ])
        with self.assertRaises(CartError):
            self.cm.commit()
        assert not CartPosition.objects.exists()

    @classscope(attr='orga')
    def test_require_bundling(self):
        self.ticket.require_bundling = True
        self.ticket.save()
        with self.assertRaises(CartError):
            self.cm.add_new_items([
                {
                    'item': self.ticket.pk,
                    'variation': None,
                    'count': 1
                }
            ])
        assert not CartPosition.objects.exists()

    @classscope(attr='orga')
    def test_bundle_item_disabled(self):
        self.ticket.active = False
        self.ticket.save()
        with self.assertRaises(CartError):
            self.cm.add_new_items([
                {
                    'item': self.ticket.pk,
                    'variation': None,
                    'count': 1
                }
            ])
        assert not CartPosition.objects.exists()

    @classscope(attr='orga')
    def test_bundle_different_tax_rates(self):
        tr19 = self.event.tax_rules.create(
            name='VAT',
            rate=Decimal('19.00')
        )
        tr7 = self.event.tax_rules.create(
            name='VAT',
            rate=Decimal('7.00'),
            price_includes_tax=True,  # will be ignored
        )
        self.event.settings.display_net_prices = True  # will be ignored
        self.ticket.tax_rule = tr19
        self.ticket.save()
        self.trans.tax_rule = tr7
        self.trans.save()
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1
            }
        ])
        self.cm.commit()
        assert CartPosition.objects.filter(addon_to__isnull=True).count() == 1
        assert CartPosition.objects.count() == 2
        cp = CartPosition.objects.filter(addon_to__isnull=True).first()
        assert cp.item == self.ticket
        assert cp.price == Decimal('21.50')
        assert cp.tax_rate == Decimal('19.00')
        assert cp.tax_value == Decimal('3.43')
        assert cp.addons.count() == 1
        assert cp.includes_tax
        a = cp.addons.first()
        assert a.item == self.trans
        assert a.price == 1.5
        assert a.tax_rate == Decimal('7.00')
        assert a.tax_value == Decimal('0.10')
        assert a.includes_tax

    @classscope(attr='orga')
    def test_one_bundled_one_addon(self):
        cat = self.event.categories.create(name="addons")
        self.trans.require_bundling = False
        self.trans.category = cat
        self.trans.save()
        ItemAddOn.objects.create(base_item=self.ticket, addon_category=cat)

        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1
            }
        ])
        self.cm.commit()

        cp = CartPosition.objects.filter(addon_to__isnull=True).first()
        assert cp.item == self.ticket
        assert cp.price == Decimal('21.50')
        b = cp.addons.first()
        assert b.item == self.trans

        self.cm = CartManager(event=self.event, cart_id=self.session_key)
        self.cm.set_addons([
            {
                'addon_to': cp.pk,
                'item': self.trans.pk,
                'variation': None
            }
        ])
        self.cm.commit()
        assert cp.addons.count() == 2
        a = cp.addons.exclude(pk=b.pk).get()
        assert a.item == self.trans
        assert a.price == 2.5

    @classscope(attr='orga')
    def test_extend_keep_price(self):
        cp = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=21.5, expires=now() - timedelta(minutes=10)
        )
        b = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=cp,
            price=1.5, expires=now() - timedelta(minutes=10), is_bundled=True
        )
        self.cm.commit()
        cp.refresh_from_db()
        b.refresh_from_db()
        assert cp.price == 21.5
        assert b.price == 1.5

    @classscope(attr='orga')
    def test_extend_designated_price_changed(self):
        cp = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=21.5, expires=now() - timedelta(minutes=10)
        )
        b = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=cp,
            price=1.5, expires=now() - timedelta(minutes=10), is_bundled=True
        )
        self.bundle1.designated_price = Decimal('2.00')
        self.bundle1.save()
        self.cm.commit()
        cp.refresh_from_db()
        b.refresh_from_db()
        assert cp.price == 21
        assert b.price == 2

    @classscope(attr='orga')
    def test_extend_designated_price_changed_beyond_base_price(self):
        cp = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=21.5, expires=now() - timedelta(minutes=10)
        )
        b = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=cp,
            price=1.5, expires=now() - timedelta(minutes=10), is_bundled=True
        )
        self.bundle1.designated_price = Decimal('40.00')
        self.bundle1.save()
        self.cm.commit()
        cp.refresh_from_db()
        b.refresh_from_db()
        assert cp.price == 0
        assert b.price == 40

    @classscope(attr='orga')
    def test_extend_base_price_changed(self):
        cp = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=21.5, expires=now() - timedelta(minutes=10)
        )
        b = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=cp,
            price=1.5, expires=now() - timedelta(minutes=10), is_bundled=True
        )
        self.ticket.default_price = Decimal('25.00')
        self.ticket.save()
        self.cm.commit()
        cp.refresh_from_db()
        b.refresh_from_db()
        assert cp.price == 23.5
        assert b.price == 1.5

    @classscope(attr='orga')
    def test_extend_bundled_and_addon(self):
        cp = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=21.5, expires=now() - timedelta(minutes=10)
        )
        a = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=cp,
            price=1.5, expires=now() - timedelta(minutes=10), is_bundled=False
        )
        b = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=cp,
            price=1.5, expires=now() - timedelta(minutes=10), is_bundled=True
        )
        self.cm.commit()
        cp.refresh_from_db()
        b.refresh_from_db()
        a.refresh_from_db()
        assert cp.price == 21.5
        assert b.price == 1.5
        assert a.price == 2.5

    @classscope(attr='orga')
    def test_expired_reverse_charge_only_bundled(self):
        tr19 = self.event.tax_rules.create(name='VAT', rate=Decimal('19.00'))
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )
        tr7 = self.event.tax_rules.create(name='VAT', rate=Decimal('7.00'), eu_reverse_charge=True, home_country=Country('DE'))
        self.ticket.tax_rule = tr19
        self.ticket.save()
        self.trans.tax_rule = tr7
        self.trans.save()

        cp = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=21.5, expires=now() - timedelta(minutes=10)
        )
        a = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=cp,
            price=1.5, expires=now() - timedelta(minutes=10), is_bundled=True
        )
        update_tax_rates(self.event, self.session_key, ia)
        cp.refresh_from_db()
        a.refresh_from_db()
        assert cp.price == Decimal('21.50')
        assert cp.tax_rate == Decimal('19.00')
        assert cp.includes_tax
        assert a.price == Decimal('1.40')
        assert a.tax_rate == Decimal('0.00')
        assert not a.includes_tax

        self.cm.invoice_address = ia
        self.cm.commit()

        cp.refresh_from_db()
        a.refresh_from_db()
        assert cp.price == Decimal('21.50')
        assert cp.tax_rate == Decimal('19.00')
        assert cp.includes_tax
        assert a.price == Decimal('1.40')
        assert a.tax_rate == 0
        assert not a.includes_tax

    @classscope(attr='orga')
    def test_expired_reverse_charge_all(self):
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )
        tr19 = self.event.tax_rules.create(name='VAT', rate=Decimal('19.00'), eu_reverse_charge=True, home_country=Country('DE'))
        tr7 = self.event.tax_rules.create(name='VAT', rate=Decimal('7.00'), eu_reverse_charge=True, home_country=Country('DE'))
        self.ticket.tax_rule = tr19
        self.ticket.save()
        self.trans.tax_rule = tr7
        self.trans.save()

        cp = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=21.5, expires=now() - timedelta(minutes=10)
        )
        a = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=cp,
            price=1.5, expires=now() - timedelta(minutes=10), is_bundled=True
        )
        update_tax_rates(self.event, self.session_key, ia)
        cp.refresh_from_db()
        a.refresh_from_db()
        assert cp.price == Decimal('18.07')
        assert cp.tax_rate == Decimal('0.00')
        assert not cp.includes_tax
        assert a.price == Decimal('1.40')
        assert a.tax_rate == Decimal('0.00')
        assert not a.includes_tax

        self.cm.invoice_address = ia
        self.cm.commit()

        cp.refresh_from_db()
        a.refresh_from_db()
        assert cp.price == Decimal('18.07')
        assert cp.tax_rate == Decimal('0.00')
        assert not cp.includes_tax
        assert a.price == Decimal('1.40')
        assert a.tax_rate == Decimal('0.00')
        assert not a.includes_tax

    @classscope(attr='orga')
    def test_reverse_charge_all_add(self):
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )
        tr19 = self.event.tax_rules.create(name='VAT', rate=Decimal('19.00'), eu_reverse_charge=True, home_country=Country('DE'))
        tr7 = self.event.tax_rules.create(name='VAT', rate=Decimal('7.00'), eu_reverse_charge=True, home_country=Country('DE'))
        self.ticket.tax_rule = tr19
        self.ticket.save()
        self.trans.tax_rule = tr7
        self.trans.save()

        self.cm.invoice_address = ia
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1
            }
        ])
        self.cm.commit()

        cp = CartPosition.objects.filter(addon_to__isnull=True).get()
        a = CartPosition.objects.filter(addon_to__isnull=False).get()
        assert cp.price == Decimal('18.07')
        assert cp.tax_rate == Decimal('0.00')
        assert not cp.includes_tax
        assert a.price == Decimal('1.40')
        assert a.tax_rate == Decimal('0.00')
        assert not a.includes_tax

    @classscope(attr='orga')
    def test_reverse_charge_bundled_add(self):
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )
        tr19 = self.event.tax_rules.create(name='VAT', rate=Decimal('19.00'))
        tr7 = self.event.tax_rules.create(name='VAT', rate=Decimal('7.00'), eu_reverse_charge=True, home_country=Country('DE'))
        self.ticket.tax_rule = tr19
        self.ticket.save()
        self.trans.tax_rule = tr7
        self.trans.save()

        self.cm.invoice_address = ia
        self.cm.add_new_items([
            {
                'item': self.ticket.pk,
                'variation': None,
                'count': 1
            }
        ])
        self.cm.commit()

        cp = CartPosition.objects.filter(addon_to__isnull=True).get()
        a = CartPosition.objects.filter(addon_to__isnull=False).get()
        assert cp.price == Decimal('21.50')
        assert cp.tax_rate == Decimal('19.00')
        assert cp.includes_tax
        assert a.price == Decimal('1.40')
        assert a.tax_rate == Decimal('0.00')
        assert not a.includes_tax


class CartSeatingTest(CartTestMixin, TestCase):

    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.plan = SeatingPlan.objects.create(
            name="Plan", organizer=self.orga, layout="{}"
        )
        self.event.seat_category_mappings.create(
            layout_category='Stalls', product=self.ticket
        )
        self.seat_a1 = self.event.seats.create(name="A1", product=self.ticket, seat_guid="A1")
        self.seat_a2 = self.event.seats.create(name="A2", product=self.ticket, seat_guid="A2")
        self.seat_a3 = self.event.seats.create(name="A3", product=self.ticket, seat_guid="A3")
        self.cm = CartManager(event=self.event, cart_id=self.session_key)

    def test_add_with_seat_without_variation(self):
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'seat_%d' % self.ticket.id: self.seat_a1.seat_guid,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
            self.assertEqual(len(objs), 1)
            self.assertEqual(objs[0].item, self.ticket)
            self.assertEqual(objs[0].seat, self.seat_a1)
            self.assertIsNone(objs[0].variation)
            self.assertEqual(objs[0].price, 23)

    def test_add_with_seat_with_missing_variation(self):
        with scopes_disabled():
            v1 = self.ticket.variations.create(value='Regular', active=True)
            self.quota_tickets.variations.add(v1)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'seat_%d' % self.ticket.id: self.seat_a1.seat_guid,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
            self.assertEqual(len(objs), 0)

    def test_add_with_seat_with_variation(self):
        with scopes_disabled():
            v1 = self.ticket.variations.create(value='Regular', active=True)
            self.quota_tickets.variations.add(v1)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'seat_%d_%d' % (self.ticket.id, v1.pk): self.seat_a1.seat_guid,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
            self.assertEqual(len(objs), 1)
            self.assertEqual(objs[0].item, self.ticket)
            self.assertEqual(objs[0].seat, self.seat_a1)
            self.assertEqual(objs[0].variation, v1)
            self.assertEqual(objs[0].price, 23)

    def test_add_with_seat_to_cart_twice(self):
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket, seat=self.seat_a1,
            price=23, expires=now() + timedelta(minutes=10)
        )
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
            self.assertEqual(len(objs), 1)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'seat_%d' % self.ticket.id: self.seat_a1.seat_guid,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
            self.assertEqual(len(objs), 1)
            self.assertEqual(objs[0].seat, self.seat_a1)

    def test_add_used_seat_to_cart(self):
        CartPosition.objects.create(
            event=self.event, cart_id='aaa', item=self.ticket, seat=self.seat_a1,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'seat_%d' % self.ticket.id: self.seat_a1.seat_guid,
        }, follow=True)
        with scopes_disabled():
            objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
            self.assertEqual(len(objs), 0)

    @scopes_disabled()
    def test_extend_seat_still_available(self):
        with scopes_disabled():
            cp = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket, seat=self.seat_a1,
                price=21.5, expires=now() - timedelta(minutes=10)
            )
        self.cm.commit()
        cp.refresh_from_db()
        assert cp.seat == self.seat_a1

    @scopes_disabled()
    def test_extend_seat_taken(self):
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket, seat=self.seat_a1,
                price=21.5, expires=now() - timedelta(minutes=10)
            )
            CartPosition.objects.create(
                event=self.event, cart_id='secondcart', item=self.ticket, seat=self.seat_a1,
                price=21.5, expires=now() + timedelta(minutes=10)
            )
        with self.assertRaises(CartError):
            self.cm.commit()

        assert not CartPosition.objects.filter(cart_id=self.session_key).exists()
