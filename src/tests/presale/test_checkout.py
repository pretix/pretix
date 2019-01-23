import datetime
import json
import os
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from bs4 import BeautifulSoup
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils.timezone import now
from django_countries.fields import Country

from pretix.base.decimal import round_decimal
from pretix.base.models import (
    CartPosition, Event, Invoice, InvoiceAddress, Item, ItemCategory, Order,
    OrderPayment, OrderPosition, Organizer, Question, QuestionAnswer, Quota,
    Voucher,
)
from pretix.base.models.items import ItemAddOn, ItemVariation, SubEventItem
from pretix.testutils.sessions import get_cart_session_key


class CheckoutTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(now().year + 1, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.stripe,pretix.plugins.banktransfer',
            live=True
        )
        self.tr19 = self.event.tax_rules.create(rate=19)
        self.category = ItemCategory.objects.create(event=self.event, name="Everything", position=0)
        self.quota_tickets = Quota.objects.create(event=self.event, name='Tickets', size=5)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          category=self.category, default_price=23, admission=True,
                                          tax_rule=self.tr19)
        self.quota_tickets.items.add(self.ticket)
        self.event.settings.set('timezone', 'UTC')
        self.event.settings.set('attendee_names_asked', False)
        self.event.settings.set('payment_banktransfer__enabled', True)

        self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.session_key = get_cart_session_key(self.client, self.event)
        self._set_session('email', 'admin@localhost')

        self.workshopcat = ItemCategory.objects.create(name="Workshops", is_addon=True, event=self.event)
        self.workshopquota = Quota.objects.create(event=self.event, name='Workshop 1', size=5)
        self.workshop1 = Item.objects.create(event=self.event, name='Workshop 1',
                                             category=self.workshopcat, default_price=Decimal('12.00'))
        self.workshop2 = Item.objects.create(event=self.event, name='Workshop 2',
                                             category=self.workshopcat, default_price=Decimal('12.00'))
        self.workshop2a = ItemVariation.objects.create(item=self.workshop2, value='A')
        self.workshop2b = ItemVariation.objects.create(item=self.workshop2, value='B')
        self.workshopquota.items.add(self.workshop1)
        self.workshopquota.items.add(self.workshop2)
        self.workshopquota.variations.add(self.workshop2a)
        self.workshopquota.variations.add(self.workshop2b)

    def _enable_reverse_charge(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )
        self._set_session('invoice_address', ia.pk)
        return ia

    def test_empty_cart(self):
        response = self.client.get('/%s/%s/checkout/start' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_timezone(self):
        """ Test basic timezone change handling by date and time questions """
        q1 = Question.objects.create(
            event=self.event, question='When did you wake up today?', type=Question.TYPE_TIME,
            required=True
        )
        q2 = Question.objects.create(
            event=self.event, question='When was your last haircut?', type=Question.TYPE_DATE,
            required=True
        )
        q3 = Question.objects.create(
            event=self.event, question='When are you going to arrive?', type=Question.TYPE_DATETIME,
            required=True
        )
        self.ticket.questions.add(q1)
        self.ticket.questions.add(q2)
        self.ticket.questions.add(q3)
        cr = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-question_%s' % (cr.id, q1.id): '06:30',
            '%s-question_%s' % (cr.id, q2.id): '2005-12-31',
            '%s-question_%s_0' % (cr.id, q3.id): '2018-01-01',
            '%s-question_%s_1' % (cr.id, q3.id): '5:23',
            'email': 'admin@localhost',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), target_status_code=200)
        self.event.settings.set('timezone', 'US/Central')
        o1 = QuestionAnswer.objects.get(question=q1)
        o2 = QuestionAnswer.objects.get(question=q2)
        o3 = QuestionAnswer.objects.get(question=q3)
        order = Order.objects.create(event=self.event, status=Order.STATUS_PAID,
                                     expires=now() + timedelta(days=3),
                                     total=4)
        op = OrderPosition.objects.create(order=order, item=self.ticket, price=42)
        o1.cartposition, o2.cartposition, o3.cartposition = None, None, None
        o1.orderposition, o2.orderposition, o3.orderposition = op, op, op
        # only time and date answers should be unaffected by timezone change
        self.assertEqual(str(o1), '06:30')
        self.assertEqual(str(o2), '2005-12-31')
        o3date, o3time = str(o3).split(' ')
        self.assertEqual(o3date, '2017-12-31')
        self.assertEqual(o3time, '23:23')

    def test_addon_questions(self):
        q1 = Question.objects.create(
            event=self.event, question='Age', type=Question.TYPE_NUMBER,
            required=True
        )
        q1.items.add(self.ticket)
        q1.items.add(self.workshop1)
        ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1,
                                 price_included=True)
        cp1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        cp1.answers.create(question=q1, answer='12')
        cp2 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.workshop1, addon_to=cp1,
            price=0, expires=now() + timedelta(minutes=10)
        )
        cp2.answers.create(question=q1, answer='12')

        self._set_session('payment', 'banktransfer')
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertEqual(OrderPosition.objects.filter(item=self.ticket).first().answers.first().answer, '12')
        self.assertEqual(OrderPosition.objects.filter(item=self.workshop1).first().answers.first().answer, '12')

    def test_questions(self):
        q1 = Question.objects.create(
            event=self.event, question='Age', type=Question.TYPE_NUMBER,
            required=True
        )
        q2 = Question.objects.create(
            event=self.event, question='How have you heard from us?', type=Question.TYPE_STRING,
            required=False
        )
        self.ticket.questions.add(q1)
        self.ticket.questions.add(q2)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        cr2 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=20, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")

        self.assertEqual(len(doc.select('input[name="%s-question_%s"]' % (cr1.id, q1.id))), 1)
        self.assertEqual(len(doc.select('input[name="%s-question_%s"]' % (cr2.id, q1.id))), 1)
        self.assertEqual(len(doc.select('input[name="%s-question_%s"]' % (cr1.id, q2.id))), 1)
        self.assertEqual(len(doc.select('input[name="%s-question_%s"]' % (cr2.id, q2.id))), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-question_%s' % (cr1.id, q1.id): '42',
            '%s-question_%s' % (cr2.id, q1.id): '',
            '%s-question_%s' % (cr1.id, q2.id): 'Internet',
            '%s-question_%s' % (cr2.id, q2.id): '',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-question_%s' % (cr1.id, q1.id): '42',
            '%s-question_%s' % (cr2.id, q1.id): '23',
            '%s-question_%s' % (cr1.id, q2.id): 'Internet',
            '%s-question_%s' % (cr2.id, q2.id): '',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1 = CartPosition.objects.get(id=cr1.id)
        cr2 = CartPosition.objects.get(id=cr2.id)
        self.assertEqual(cr1.answers.filter(question=q1).count(), 1)
        self.assertEqual(cr2.answers.filter(question=q1).count(), 1)
        self.assertEqual(cr1.answers.filter(question=q2).count(), 1)
        self.assertFalse(cr2.answers.filter(question=q2).exists())

    def test_reverse_charge(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )

        with mock.patch('vat_moss.id.validate') as mock_validate:
            mock_validate.return_value = ('AT', 'AT123456', 'Foo')
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '12345',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == round_decimal(Decimal('23.00') / Decimal('1.19'))

        ia = InvoiceAddress.objects.get(pk=self.client.session['carts'][self.session_key].get('invoice_address'))
        assert ia.vat_id_validated

    def test_reverse_charge_enable_then_disable(self):
        self.test_reverse_charge()

        with mock.patch('vat_moss.id.validate') as mock_validate:
            mock_validate.return_value = ('AT', 'AT123456', 'Foo')
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'individual',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '12345',
                'city': 'Here',
                'country': 'AT',
                'vat_id': '',
                'email': 'admin@localhost'
            }, follow=True)

        cr = CartPosition.objects.get(cart_id=self.session_key)
        assert cr.price == Decimal('23.00')

        ia = InvoiceAddress.objects.get(pk=self.client.session['carts'][self.session_key].get('invoice_address'))
        assert not ia.vat_id_validated

    def test_reverse_charge_invalid_vatid(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )

        with mock.patch('vat_moss.id.validate') as mock_validate:
            def raiser(*args, **kwargs):
                import vat_moss.errors
                raise vat_moss.errors.InvalidError()

            mock_validate.side_effect = raiser
            resp = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '12345',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)
            assert 'alert-danger' in resp.rendered_content

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.00')

    def test_reverse_charge_vatid_non_eu(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('NO')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )

        with mock.patch('vat_moss.id.validate') as mock_validate:
            mock_validate.return_value = ('AU', 'AU123456', 'Foo')
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '12345',
                'city': 'Here',
                'country': 'AU',
                'vat_id': 'AU123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == round_decimal(Decimal('23.00') / Decimal('1.19'))

        ia = InvoiceAddress.objects.get(pk=self.client.session['carts'][self.session_key].get('invoice_address'))
        assert not ia.vat_id_validated

    def test_reverse_charge_vatid_same_country(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('AT')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )

        with mock.patch('vat_moss.id.validate') as mock_validate:
            mock_validate.return_value = ('AT', 'AT123456', 'Foo')
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '12345',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.00')

        ia = InvoiceAddress.objects.get(pk=self.client.session['carts'][self.session_key].get('invoice_address'))
        assert ia.vat_id_validated

    def test_reverse_charge_vatid_check_invalid_country(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )

        with mock.patch('vat_moss.id.validate') as mock_validate:
            mock_validate.return_value = ('AT', 'AT123456', 'Foo')
            resp = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '12345',
                'city': 'Here',
                'country': 'FR',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)
            assert 'alert-danger' in resp.rendered_content

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.00')

    def test_reverse_charge_vatid_check_unavailable(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )

        with mock.patch('vat_moss.id.validate') as mock_validate:
            def raiser(*args, **kwargs):
                import vat_moss.errors
                raise vat_moss.errors.WebServiceUnavailableError('Fail')

            mock_validate.side_effect = raiser
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '12345',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.00')

        ia = InvoiceAddress.objects.get(pk=self.client.session['carts'][self.session_key].get('invoice_address'))
        assert not ia.vat_id_validated

    def test_custom_tax_rules(self):
        self.tr19.custom_rules = json.dumps([
            {'country': 'AT', 'address_type': 'business_vat_id', 'action': 'reverse'},
            {'country': 'ZZ', 'address_type': '', 'action': 'vat'},
        ])
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )

        with mock.patch('vat_moss.id.validate') as mock_validate:
            mock_validate.return_value = ('AT', 'AT123456', 'Foo')
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '12345',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('19.33')

        with mock.patch('vat_moss.id.validate') as mock_validate:
            mock_validate.return_value = ('DE', 'DE123456', 'Foo')
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '12345',
                'city': 'Here',
                'country': 'DE',
                'vat_id': 'DE123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.00')

    def test_question_file_upload(self):
        q1 = Question.objects.create(
            event=self.event, question='Student ID', type=Question.TYPE_FILE,
            required=False
        )
        self.ticket.questions.add(q1)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")

        self.assertEqual(len(doc.select('input[name="%s-question_%s"]' % (cr1.id, q1.id))), 1)

        f = SimpleUploadedFile("testfile.txt", b"file_content")
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-question_%s' % (cr1.id, q1.id): f,
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1 = CartPosition.objects.get(id=cr1.id)
        a = cr1.answers.get(question=q1)
        assert a.file
        assert a.file.read() == b"file_content"
        assert os.path.exists(os.path.join(settings.MEDIA_ROOT, a.file.name))

        # Delete
        self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-question_%s-clear' % (cr1.id, q1.id): 'on',
            'email': 'admin@localhost'
        }, follow=True)
        assert not cr1.answers.exists()
        assert not os.path.exists(os.path.join(settings.MEDIA_ROOT, a.file.name))

    def test_attendee_email_required(self):
        self.event.settings.set('attendee_emails_asked', True)
        self.event.settings.set('attendee_emails_required', True)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="%s-attendee_email"]' % cr1.id)), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-attendee_email' % cr1.id: '',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-attendee_email' % cr1.id: 'foo@localhost',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.attendee_email, 'foo@localhost')

    def test_attendee_name_required(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', True)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_0"]' % cr1.id)), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-attendee_name_parts_0' % cr1.id: '',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-attendee_name_parts_0' % cr1.id: 'Peter',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.attendee_name, 'Peter')

    def test_attendee_name_scheme(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', True)
        self.event.settings.set('name_scheme', 'title_given_middle_family')
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_0"]' % cr1.id)), 1)
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_1"]' % cr1.id)), 1)
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_2"]' % cr1.id)), 1)
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_3"]' % cr1.id)), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-attendee_name_parts_0' % cr1.id: 'Mr',
            '%s-attendee_name_parts_1' % cr1.id: 'John',
            '%s-attendee_name_parts_2' % cr1.id: 'F',
            '%s-attendee_name_parts_3' % cr1.id: 'Kennedy',
            'email': 'admin@localhost'
        })
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.attendee_name, 'Mr John F Kennedy')
        self.assertEqual(cr1.attendee_name_parts, {
            'given_name': 'John',
            'title': 'Mr',
            'middle_name': 'F',
            'family_name': 'Kennedy',
            "_scheme": "title_given_middle_family"
        })

    def test_attendee_name_optional(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', False)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_0"]' % cr1.id)), 1)

        # Not all fields filled out, expect success
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-attendee_name_parts_0' % cr1.id: '',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1 = CartPosition.objects.get(id=cr1.id)
        assert not cr1.attendee_name

    def test_invoice_address_required(self):
        self.event.settings.invoice_address_asked = True
        self.event.settings.invoice_address_required = True
        self.event.settings.set('name_scheme', 'title_given_middle_family')

        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="city"]')), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'city': 'Here',
            'country': 'DE',
            'vat_id': 'DE123456',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'company': 'Foo',
            'name_parts_0': 'Mr',
            'name_parts_1': 'John',
            'name_parts_2': '',
            'name_parts_3': 'Kennedy',
            'street': 'Baz',
            'zipcode': '12345',
            'city': 'Here',
            'country': 'DE',
            'vat_id': 'DE123456',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        ia = InvoiceAddress.objects.last()
        assert ia.name_parts == {
            'title': 'Mr',
            'given_name': 'John',
            'middle_name': '',
            'family_name': 'Kennedy',
            "_scheme": "title_given_middle_family"
        }
        assert ia.name_cached == 'Mr John Kennedy'

    def test_invoice_address_optional(self):
        self.event.settings.invoice_address_asked = True
        self.event.settings.invoice_address_required = False

        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="city"]')), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'city': 'Here',
            'country': 'DE',
            'vat_id': 'DE123456',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_invoice_name_required(self):
        self.event.settings.invoice_address_asked = False
        self.event.settings.invoice_name_required = True

        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="name_parts_0"]')), 1)
        self.assertEqual(len(doc.select('input[name="street"]')), 0)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'name_parts_0': 'Raphael',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_payment(self):
        # TODO: Test for correct payment method fees
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 2)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_payment_max_value(self):
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__total_max', Decimal('42.00'))
        self.event.settings.set('payment_banktransfer__enabled', True)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 2)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 1)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert doc.select(".alert-danger")

    def test_payment_min_value(self):
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__total_min', Decimal('42.00'))
        self.event.settings.set('payment_banktransfer__enabled', True)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 1)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert doc.select(".alert-danger")

    def test_payment_country_ignored_without_invoice_address_required(self):
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__restricted_countries', ['DE', 'AT'])
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('invoice_address_required', False)
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('CH')
        )
        self._set_session('invoice_address', ia.pk)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 2)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert not doc.select(".alert-danger")

    def test_payment_country_allowed(self):
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__restricted_countries', ['DE', 'AT'])
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('invoice_address_required', True)
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('DE'), name_parts={'full_name': 'Foo', "_scheme": "full"}, name_cached='Foo', street='Foo'
        )
        self._set_session('invoice_address', ia.pk)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 2)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert not doc.select(".alert-danger")

    def test_payment_country_blocked(self):
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__restricted_countries', ['DE', 'AT'])
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('invoice_address_required', True)
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('CH'), name_parts={'full_name': 'Foo', "_scheme": "full"}, name_cached='Foo', street='Foo'
        )
        self._set_session('invoice_address', ia.pk)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 1)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert doc.select(".alert-danger")

    def test_premature_confirm(self):
        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )

        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        self._set_session('payment', 'banktransfer')

        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', True)

        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1.attendee_name_parts = {"full_name": 'Peter', "_scheme": "full"}
        cr1.save()
        q1 = Question.objects.create(
            event=self.event, question='Age', type=Question.TYPE_NUMBER,
            required=True
        )
        self.ticket.questions.add(q1)

        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        q1.required = False
        q1.save()
        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertEqual(response.status_code, 200)

        self._set_session('email', 'invalid')
        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def _set_session(self, key, value):
        session = self.client.session
        session['carts'][get_cart_session_key(self.client, self.event)][key] = value
        session.save()

    def test_subevent(self):
        self.event.has_subevents = True
        self.event.save()
        se = self.event.subevents.create(name='Foo', date_from=now())
        q = se.quotas.create(name="foo", size=None, event=self.event)
        q.items.add(self.ticket)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10), subevent=se
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.first().subevent, se)

    def test_require_approval_no_payment_step(self):
        self.event.settings.invoice_generate = 'True'
        self.ticket.require_approval = True
        self.ticket.save()
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=42, expires=now() + timedelta(minutes=10)
        )

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        print(doc)
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.first().status, Order.STATUS_PENDING)
        self.assertTrue(Order.objects.first().require_approval)
        self.assertEqual(OrderPosition.objects.count(), 1)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_require_approval_no_payment_step_free(self):
        self.ticket.require_approval = True
        self.ticket.save()
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=0, expires=now() + timedelta(minutes=10)
        )

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.first().status, Order.STATUS_PENDING)
        self.assertTrue(Order.objects.first().require_approval)
        self.assertEqual(OrderPosition.objects.count(), 1)

    def test_require_approval_in_addon_to_free(self):
        ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1,
                                 price_included=True)
        cp1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=0, expires=now() - timedelta(minutes=10)
        )
        self.ticket.default_price = 0
        self.ticket.save()
        self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)

        self.workshop1.require_approval = True
        self.workshop1.save()
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.workshop1,
            price=0, expires=now() - timedelta(minutes=10),
            addon_to=cp1
        )
        self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cp1.id).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.first().status, Order.STATUS_PENDING)
        self.assertTrue(Order.objects.first().require_approval)
        self.assertEqual(OrderPayment.objects.count(), 0)
        self.assertEqual(OrderPosition.objects.count(), 2)

    def test_free_price(self):
        self.ticket.free_price = True
        self.ticket.save()
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=42, expires=now() + timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.first().price, 42)

    def test_confirm_in_time(self):
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.count(), 1)

    def test_subevent_confirm_expired_available(self):
        self.event.has_subevents = True
        self.event.save()
        se = self.event.subevents.create(name='Foo', date_from=now())
        se2 = self.event.subevents.create(name='Foo', date_from=now())
        self.quota_tickets.size = 0
        self.quota_tickets.subevent = se2
        self.quota_tickets.save()
        q2 = se.quotas.create(event=self.event, size=1, name='Bar')
        q2.items.add(self.ticket)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10), subevent=se
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.count(), 1)

    def test_confirm_expired_available(self):
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.count(), 1)

    def test_subevent_confirm_price_changed(self):
        self.event.has_subevents = True
        self.event.save()
        se = self.event.subevents.create(name='Foo', date_from=now())
        q = se.quotas.create(name="foo", size=None, event=self.event)
        q.items.add(self.ticket)
        SubEventItem.objects.create(subevent=se, item=self.ticket, price=24)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10), subevent=se
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.price, 24)

    def test_addon_price_included(self):
        ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1,
                                 price_included=True)
        cp1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.workshop1,
            price=0, expires=now() - timedelta(minutes=10),
            addon_to=cp1
        )

        self._set_session('payment', 'banktransfer')
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertEqual(OrderPosition.objects.filter(item=self.workshop1).last().price, 0)

    def test_confirm_price_changed_reverse_charge(self):
        self._enable_reverse_charge()
        self.ticket.default_price = 24
        self.ticket.save()
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.price, round_decimal(Decimal('24.00') / Decimal('1.19')))

    def test_confirm_price_changed(self):
        self.ticket.default_price = 24
        self.ticket.save()
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.price, 24)

    def test_confirm_free_price_increased(self):
        self.ticket.default_price = 24
        self.ticket.free_price = True
        self.ticket.save()
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.price, 24)

    def test_voucher(self):
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                   valid_until=now() + timedelta(days=2))
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() + timedelta(minutes=10), voucher=v
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.first().voucher, v)
        self.assertEqual(Voucher.objects.get(pk=v.pk).redeemed, 1)

    def test_voucher_required(self):
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                   valid_until=now() + timedelta(days=2))
        self.ticket.require_voucher = True
        self.ticket.save()
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() + timedelta(minutes=10), voucher=v
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertEqual(Voucher.objects.get(pk=v.pk).redeemed, 1)

    def test_voucher_required_but_missing(self):
        self.ticket.require_voucher = True
        self.ticket.save()
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() + timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert doc.select(".alert-danger")

    def test_voucher_price_changed(self):
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                   valid_until=now() + timedelta(days=2))
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=13, expires=now() - timedelta(minutes=10), voucher=v
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.price, Decimal('12.00'))

    def test_voucher_redeemed(self):
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                   valid_until=now() + timedelta(days=2), redeemed=1)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        self._set_session('payment', 'banktransfer')
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn("has already been", doc.select(".alert-danger")[0].text)

    def test_voucher_multiuse_redeemed(self):
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                   valid_until=now() + timedelta(days=2), max_usages=3, redeemed=3)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        self._set_session('payment', 'banktransfer')
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn("has already been", doc.select(".alert-danger")[0].text)

    def test_voucher_multiuse_partially(self):
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                   valid_until=now() + timedelta(days=2), max_usages=3, redeemed=2)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        self._set_session('payment', 'banktransfer')
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn("has already been", doc.select(".alert-danger")[0].text)
        assert CartPosition.objects.filter(cart_id=self.session_key).count() == 1

    def test_voucher_multiuse_ok(self):
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                   valid_until=now() + timedelta(days=2), max_usages=3, redeemed=1)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        self._set_session('payment', 'banktransfer')
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.count(), 2)
        v.refresh_from_db()
        assert v.redeemed == 3

    def test_voucher_multiuse_in_other_cart_expired(self):
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                   price_mode='set',
                                   valid_until=now() + timedelta(days=2), max_usages=3, redeemed=1)
        CartPosition.objects.create(
            event=self.event, cart_id='other', item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        self._set_session('payment', 'banktransfer')
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.count(), 2)
        v.refresh_from_db()
        assert v.redeemed == 3

    def test_voucher_multiuse_in_other_cart(self):
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                   valid_until=now() + timedelta(days=2), max_usages=3, redeemed=1)
        CartPosition.objects.create(
            event=self.event, cart_id='other', item=self.ticket,
            price=12, expires=now() + timedelta(minutes=10), voucher=v
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        self._set_session('payment', 'banktransfer')
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn("has already been", doc.select(".alert-danger")[0].text)
        assert CartPosition.objects.filter(cart_id=self.session_key).count() == 1

    def test_voucher_ignore_quota(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                   valid_until=now() + timedelta(days=2), allow_ignore_quota=True)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.count(), 1)

    def test_voucher_block_quota(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                   valid_until=now() + timedelta(days=2), block_quota=True)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key).count(), 1)

        cr1.voucher = v
        cr1.save()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.count(), 1)

    def test_voucher_block_quota_other_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        q2 = self.event.quotas.create(name='Testquota', size=0)
        q2.items.add(self.ticket)
        v = Voucher.objects.create(quota=self.quota_tickets, value=Decimal('12.00'), event=self.event,
                                   valid_until=now() + timedelta(days=2), block_quota=True)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=12, expires=now() - timedelta(minutes=10), voucher=v
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertTrue(doc.select(".alert-danger"))
        self.assertFalse(Order.objects.exists())

    def test_voucher_double(self):
        self.quota_tickets.size = 2
        self.quota_tickets.save()
        v = Voucher.objects.create(item=self.ticket, event=self.event,
                                   valid_until=now() + timedelta(days=2), block_quota=True)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10), voucher=v
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10), voucher=v
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, voucher=v).count(), 1)
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        self.assertFalse(Order.objects.exists())

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, voucher=v).exists())
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.count(), 1)

    def test_max_per_item_failed(self):
        self.quota_tickets.size = 3
        self.quota_tickets.save()
        self.ticket.max_per_order = 1
        self.ticket.save()
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10),
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10),
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key).count(), 1)
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        self.assertFalse(Order.objects.exists())

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderPosition.objects.count(), 1)

    def test_subevent_confirm_expired_partial(self):
        self.event.has_subevents = True
        self.event.save()
        se = self.event.subevents.create(name='Foo', date_from=now())
        se2 = self.event.subevents.create(name='Foo', date_from=now())
        self.quota_tickets.size = 10
        self.quota_tickets.subevent = se2
        self.quota_tickets.save()
        q2 = se.quotas.create(event=self.event, size=1, name='Bar')
        q2.items.add(self.ticket)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10), subevent=se
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10), subevent=se
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10), subevent=se2
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key).count(), 2)

    def test_confirm_expired_partial(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key).count(), 1)

    def test_confirm_event_over(self):
        self.event.date_to = now() - datetime.timedelta(days=1)
        self.event.save()
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)

    def test_confirm_presale_over(self):
        self.event.presale_end = now() - datetime.timedelta(days=1)
        self.event.save()
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)

    def test_confirm_require_voucher(self):
        self.ticket.require_voucher = True
        self.ticket.save()
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_require_hide_without_voucher(self):
        self.ticket.require_voucher = True
        self.ticket.save()
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_no_longer_available(self):
        self.ticket.available_until = now() - timedelta(days=1)
        self.ticket.save()
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_inactive(self):
        self.ticket.active = False
        self.ticket.save()
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_expired_unavailable(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_completely_unavailable(self):
        self.quota_tickets.items.remove(self.ticket)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_expired_with_blocking_voucher_unavailable(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        v = Voucher.objects.create(quota=self.quota_tickets, event=self.event, block_quota=True)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket, voucher=v,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)

    def test_confirm_expired_with_non_blocking_voucher_unavailable(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        v = Voucher.objects.create(quota=self.quota_tickets, event=self.event)
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket, voucher=v,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_not_expired_with_blocking_voucher_unavailable(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        v = Voucher.objects.create(quota=self.quota_tickets, event=self.event, block_quota=True)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket, voucher=v,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)

    def test_confirm_not_expired_with_non_blocking_voucher_unavailable(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        v = Voucher.objects.create(quota=self.quota_tickets, event=self.event)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket, voucher=v,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)

    def test_addons_as_first_step(self):
        ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )

        response = self.client.get('/%s/%s/checkout/start' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_set_addons_item_and_variation(self):
        ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat)
        cp1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        cp2 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )

        response = self.client.post('/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug), {
            '{}_{}-item_{}'.format(cp1.pk, self.workshopcat.pk, self.workshop1.pk): 'on',
            '{}_{}-item_{}'.format(cp2.pk, self.workshopcat.pk, self.workshop2.pk): self.workshop2a.pk,
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert cp1.addons.first().item == self.workshop1
        assert cp2.addons.first().item == self.workshop2
        assert cp2.addons.first().variation == self.workshop2a

    def test_set_addons_required(self):
        ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )

        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug))
        self.assertRedirects(response, '/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        response = self.client.get('/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug))
        assert 'Workshop 1' in response.rendered_content
        assert '€12.00' in response.rendered_content

    def test_set_addons_included(self):
        ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1,
                                 price_included=True)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )

        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'Workshop 1' in response.rendered_content
        assert '€12.00' not in response.rendered_content

    def test_set_addons_subevent(self):
        self.event.has_subevents = True
        self.event.save()
        se = self.event.subevents.create(name='Foo', date_from=now())
        self.workshopquota.size = 1
        self.workshopquota.subevent = se
        self.workshopquota.save()
        SubEventItem.objects.create(subevent=se, item=self.workshop1, price=42)

        ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10), subevent=se
        )

        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'Workshop 1 (+ €42.00)' in response.rendered_content

    def test_set_addons_subevent_net_prices(self):
        self.event.has_subevents = True
        self.event.settings.display_net_prices = True
        self.event.save()
        se = self.event.subevents.create(name='Foo', date_from=now())
        self.workshopquota.size = 1
        self.workshopquota.subevent = se
        self.workshopquota.save()
        self.workshop1.tax_rule = self.event.tax_rules.get_or_create(rate=Decimal('19.00'), name="VAT")[0]
        self.workshop1.save()
        self.workshop2.tax_rule = self.event.tax_rules.get_or_create(rate=Decimal('19.00'), name="VAT")[0]
        self.workshop2.save()
        SubEventItem.objects.create(subevent=se, item=self.workshop1, price=42)

        ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10), subevent=se
        )

        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'Workshop 1 (+ €35.29 plus 19.00% VAT)' in response.rendered_content
        assert 'A (+ €10.08 plus 19.00% VAT)' in response.rendered_content

    def test_confirm_subevent_presale_not_yet(self):
        self.event.has_subevents = True
        self.event.settings.display_net_prices = True
        self.event.save()
        se = self.event.subevents.create(name='Foo', date_from=now(), presale_start=now() + datetime.timedelta(days=1))
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10), subevent=se
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        assert 'presale period for one of the events in your cart has not yet started.' in response.rendered_content
        assert not CartPosition.objects.filter(cart_id=self.session_key).exists()

    def test_confirm_subevent_presale_over(self):
        self.event.has_subevents = True
        self.event.settings.display_net_prices = True
        self.event.save()
        se = self.event.subevents.create(name='Foo', date_from=now(), presale_end=now() - datetime.timedelta(days=1))
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10), subevent=se
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        assert 'presale period for one of the events in your cart has ended.' in response.rendered_content
        assert not CartPosition.objects.filter(cart_id=self.session_key).exists()

    def test_confirm_subevent_ignore_series_dates(self):
        self.event.has_subevents = True
        self.event.date_to = now() - datetime.timedelta(days=1)
        self.event.save()
        se = self.event.subevents.create(name='Foo', date_from=now(), presale_end=now() + datetime.timedelta(days=1))
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10), subevent=se
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
