import datetime
import time
from unittest import expectedFailure
from bs4 import BeautifulSoup
from django.test import TestCase
from django.utils.timezone import now
from datetime import timedelta

from pretix.base.models import Item, Organizer, Event, ItemCategory, Quota, Property, PropertyValue, ItemVariation, User, \
    CartPosition, Question


class CheckoutTestCase(TestCase):

    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.stripe,pretix.plugins.banktransfer'
        )
        self.user = User.objects.create_local_user(self.event, 'demo', 'demo')
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
                                          category=self.category, default_price=23, admission=True)
        self.quota_tickets.items.add(self.ticket)
        self.assertTrue(self.client.login(username='demo@%s.event.pretix' % self.event.identity, password='demo'))

    def test_empty_cart(self):
        response = self.client.get('/%s/%s/checkout' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_no_questions(self):
        self.event.settings.set('attendee_names_asked', False)
        CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=20, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_questions(self):
        self.event.settings.set('attendee_names_asked', False)
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
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        cr2 = CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=20, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content)

        self.assertEqual(len(doc.select('input[name=%s-question_%s]' % (cr1.identity, q1.identity))), 1)
        self.assertEqual(len(doc.select('input[name=%s-question_%s]' % (cr2.identity, q1.identity))), 1)
        self.assertEqual(len(doc.select('input[name=%s-question_%s]' % (cr1.identity, q2.identity))), 1)
        self.assertEqual(len(doc.select('input[name=%s-question_%s]' % (cr2.identity, q2.identity))), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout' % (self.orga.slug, self.event.slug), {
            '%s-question_%s' % (cr1.identity, q1.identity): '42',
            '%s-question_%s' % (cr2.identity, q1.identity): '',
            '%s-question_%s' % (cr1.identity, q2.identity): 'Internet',
            '%s-question_%s' % (cr2.identity, q2.identity): '',
            }, follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout' % (self.orga.slug, self.event.slug), {
            '%s-question_%s' % (cr1.identity, q1.identity): '42',
            '%s-question_%s' % (cr2.identity, q1.identity): '23',
            '%s-question_%s' % (cr1.identity, q2.identity): 'Internet',
            '%s-question_%s' % (cr2.identity, q2.identity): '',
            }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1 = CartPosition.objects.current.get(identity=cr1.identity)
        cr2 = CartPosition.objects.current.get(identity=cr2.identity)
        self.assertEqual(cr1.answers.filter(question=q1).count(), 1)
        self.assertEqual(cr2.answers.filter(question=q1).count(), 1)
        self.assertEqual(cr1.answers.filter(question=q2).count(), 1)
        self.assertFalse(cr2.answers.filter(question=q2).exists())

    @expectedFailure
    def test_boolean_required_question(self):
        """
        Expected to fail. See https://github.com/pretix/pretix/issues/19
        """
        self.event.settings.set('attendee_names_asked', False)
        q1 = Question.objects.create(
            event=self.event, question='Breakfast', type=Question.TYPE_BOOLEAN,
            required=True
        )
        self.ticket.questions.add(q1)
        cr1 = CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select('input[name=%s-question_%s]' % (cr1.identity, q1.identity))), 1)

        response = self.client.post('/%s/%s/checkout' % (self.orga.slug, self.event.slug), {
            '%s-question_%s' % (cr1.identity, q1.identity): '',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1 = CartPosition.objects.current.get(identity=cr1.identity)
        self.assertEqual(cr1.answers.filter(question=q1).count(), 1)
        self.assertEqual(cr1.answers.get(question=q1).value, 'False')

    def test_attendee_name_required(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', True)
        cr1 = CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select('input[name=%s-attendee_name]' % cr1.identity)), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout' % (self.orga.slug, self.event.slug), {
            '%s-attendee_name' % cr1.identity: '',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout' % (self.orga.slug, self.event.slug), {
            '%s-attendee_name' % cr1.identity: 'Peter',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1 = CartPosition.objects.current.get(identity=cr1.identity)
        self.assertEqual(cr1.attendee_name, 'Peter')

    def test_attendee_name_optional(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('atendee_names_required', False)
        cr1 = CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select('input[name=%s-attendee_name]' % cr1.identity)), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout' % (self.orga.slug, self.event.slug), {
            '%s-attendee_name' % cr1.identity: '',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1 = CartPosition.objects.current.get(identity=cr1.identity)
        self.assertIsNone(cr1.attendee_name)

    def test_payment(self):
        # TODO: Test for payment method fees
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout/payment' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select('input[name=payment]')), 2)
        response = self.client.post('/%s/%s/checkout/payment' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/confirm' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
