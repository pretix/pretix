import datetime
from bs4 import BeautifulSoup
from django.test import TestCase
from django.utils.timezone import now
from datetime import timedelta

from pretix.base.models import Item, Organizer, Event, ItemCategory, Quota, User, \
    CartPosition, Question, Order, OrderPosition


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
        self.quota_tickets = Quota.objects.create(event=self.event, name='Tickets', size=5)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          category=self.category, default_price=23, admission=True)
        self.quota_tickets.items.add(self.ticket)
        self.assertTrue(self.client.login(username='demo@%s.event.pretix' % self.event.identity, password='demo'))
        self.event.settings.set('attendee_names_asked', False)
        self.event.settings.set('payment_banktransfer__enabled', True)

    def test_empty_cart(self):
        response = self.client.get('/%s/%s/checkout' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_no_questions(self):
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
        self.event.settings.set('attendee_names_required', False)
        cr1 = CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.get('/%s/%s/checkout' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select('input[name=%s-attendee_name]' % cr1.identity)), 1)

        # Not all fields filled out, expect success
        response = self.client.post('/%s/%s/checkout' % (self.orga.slug, self.event.slug), {
            '%s-attendee_name' % cr1.identity: '',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1 = CartPosition.objects.current.get(identity=cr1.identity)
        self.assertIsNone(cr1.attendee_name)

    def test_payment(self):
        # TODO: Test for correct payment method fees
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

    def test_premature_confirm(self):
        response = self.client.get('/%s/%s/checkout/confirm' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        cr1 = CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )

        response = self.client.get('/%s/%s/checkout/confirm' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        self._set_session('payment', 'banktransfer')

        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', True)

        response = self.client.get('/%s/%s/checkout/confirm' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1 = cr1.clone()
        cr1.attendee_name = 'Peter'
        cr1.save()
        q1 = Question.objects.create(
            event=self.event, question='Age', type=Question.TYPE_NUMBER,
            required=True
        )
        self.ticket.questions.add(q1)

        response = self.client.get('/%s/%s/checkout/confirm' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        q1 = q1.clone()
        q1.required = False
        q1.save()
        response = self.client.get('/%s/%s/checkout/confirm' % (self.orga.slug, self.event.slug), follow=True)
        self.assertEqual(response.status_code, 200)

    def _set_session(self, key, value):
        session = self.client.session
        session[key] = value
        session.save()

    def test_confirm_in_time(self):
        cr1 = CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select(".alert-success")), 1)
        self.assertFalse(CartPosition.objects.current.filter(identity=cr1.identity).exists())
        self.assertEqual(len(Order.objects.current.filter(user=self.user)), 1)
        self.assertEqual(len(OrderPosition.objects.current.filter(order__user=self.user)), 1)

    def test_confirm_expired_available(self):
        cr1 = CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select(".alert-success")), 1)
        self.assertFalse(CartPosition.objects.current.filter(identity=cr1.identity).exists())
        self.assertEqual(len(Order.objects.current.filter(user=self.user)), 1)
        self.assertEqual(len(OrderPosition.objects.current.filter(order__user=self.user)), 1)

    def test_confirm_price_changed(self):
        self.ticket = self.ticket.clone()
        self.ticket.default_price = 24
        self.ticket.save()
        cr1 = CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        cr1 = CartPosition.objects.current.get(identity=cr1.identity)
        self.assertEqual(cr1.price, 24)

    def test_confirm_expired_partial(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        self.assertEqual(CartPosition.objects.current.filter(user=self.user).count(), 1)

    def test_confirm_expired_unavailable(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        cr1 = CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        self.assertFalse(CartPosition.objects.current.filter(identity=cr1.identity).exists())

    def test_confirm_completely_unavailable(self):
        self.quota_tickets.items.remove(self.ticket)
        CartPosition.objects.create(
            event=self.event, user=self.user, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self._set_session('payment', 'banktransfer')

        response = self.client.post('/%s/%s/checkout/confirm' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select(".alert-danger")), 1)
