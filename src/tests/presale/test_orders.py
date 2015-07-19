import datetime
from decimal import Decimal

from bs4 import BeautifulSoup
from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import (
    Event, Item, ItemCategory, ItemVariation, Order, OrderPosition, Organizer,
    Property, PropertyValue, Question, Quota, User,
)


class OrdersTest(TestCase):

    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.stripe,pretix.plugins.banktransfer,tests.testdummy'
        )
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('ticketoutput_testdummy__enabled', True)
        self.user = User.objects.create_local_user(self.event, 'demo', 'foo')
        self.user2 = User.objects.create_local_user(self.event, 'bar', 'foo')
        self.assertTrue(self.client.login(username='demo@%s.event.pretix' % self.event.identity, password='foo'))

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
                                          category=self.category, default_price=23,
                                          admission=True)
        self.quota_tickets.items.add(self.ticket)
        self.event.settings.set('attendee_names_asked', True)
        self.question = Question.objects.create(question='Foo', type=Question.TYPE_STRING, event=self.event,
                                                required=False)
        self.ticket.questions.add(self.question)

        self.order = Order.objects.create(
            status=Order.STATUS_PENDING,
            event=self.event,
            user=self.user,
            datetime=now() - datetime.timedelta(days=3),
            expires=now() + datetime.timedelta(days=11),
            total=Decimal("23"),
            payment_provider='banktransfer'
        )
        self.ticket_pos = OrderPosition.objects.create(
            order=self.order,
            item=self.ticket,
            variation=None,
            price=Decimal("14"),
            attendee_name="Peter"
        )
        self.not_my_order = Order.objects.create(
            status=Order.STATUS_PENDING,
            event=self.event,
            user=self.user2,
            datetime=now() - datetime.timedelta(days=3),
            expires=now() + datetime.timedelta(days=11),
            total=Decimal("23")
        )

    def test_orders_list(self):
        response = self.client.get(
            '/%s/%s/orders' % (self.orga.slug, self.event.slug)
        )
        doc = BeautifulSoup(response.rendered_content)
        rows = doc.select("table tbody tr")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn(self.order.code, row.text)
        self.assertIn(str(self.order.total), row.text)

    def test_unknown_order(self):
        response = self.client.get(
            '/%s/%s/order/ABCDE/' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/%s/' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/ABCDE/pay' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/%s/pay' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/ABCDE/pay/confirm' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/%s/pay/confirm' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/ABCDE/modify' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/%s/modify' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/ABCDE/cancel' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/%s/cancel' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404

    def test_orders_detail(self):
        response = self.client.get(
            '/%s/%s/order/%s/' % (self.orga.slug, self.event.slug, self.order.code)
        )
        assert response.status_code == 200
        doc = BeautifulSoup(response.rendered_content)
        assert len(doc.select(".cart-row")) > 0
        assert "pending" in doc.select(".label-warning")[0].text.lower()

    def test_orders_modify_invalid(self):
        self.order.status = Order.STATUS_REFUNDED
        self.order.save()
        response = self.client.get(
            '/%s/%s/order/%s/modify' % (self.orga.slug, self.event.slug, self.order.code)
        )
        assert response.status_code == 403

    def test_orders_modify_attendee_optional(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', False)

        response = self.client.get('/%s/%s/order/%s/modify' % (self.orga.slug, self.event.slug, self.order.code))
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select('input[name=%s-attendee_name]' % self.ticket_pos.identity)), 1)

        # Not all fields filled out, expect success
        response = self.client.post('/%s/%s/order/%s/modify' % (self.orga.slug, self.event.slug, self.order.code), {
            '%s-attendee_name' % self.ticket_pos.identity: '',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/order/%s/' % (self.orga.slug, self.event.slug, self.order.code),
                             target_status_code=200)
        self.ticket_pos = OrderPosition.objects.current.get(identity=self.ticket_pos.identity)
        assert self.ticket_pos.attendee_name in (None, '')

    def test_orders_modify_attendee_required(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', True)

        response = self.client.get('/%s/%s/order/%s/modify' % (self.orga.slug, self.event.slug, self.order.code))
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select('input[name=%s-attendee_name]' % self.ticket_pos.identity)), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/order/%s/modify' % (self.orga.slug, self.event.slug, self.order.code), {
            '%s-attendee_name' % self.ticket_pos.identity: '',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        response = self.client.post('/%s/%s/order/%s/modify' % (self.orga.slug, self.event.slug, self.order.code), {
            '%s-attendee_name' % self.ticket_pos.identity: 'Peter',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/order/%s/' % (self.orga.slug, self.event.slug, self.order.code),
                             target_status_code=200)
        self.ticket_pos = OrderPosition.objects.current.get(identity=self.ticket_pos.identity)
        assert self.ticket_pos.attendee_name == 'Peter'

    def test_orders_questions_optional(self):
        self.event.settings.set('attendee_names_asked', False)
        self.event.settings.set('attendee_names_required', False)

        response = self.client.get('/%s/%s/order/%s/modify' % (self.orga.slug, self.event.slug, self.order.code))
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select('input[name=%s-question_%s]' % (
            self.ticket_pos.identity, self.question.identity))), 1)

        # Not all fields filled out, expect success
        response = self.client.post('/%s/%s/order/%s/modify' % (self.orga.slug, self.event.slug, self.order.code), {
            '%s-question_%s' % (self.ticket_pos.identity, self.question.identity): '',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/order/%s/' % (self.orga.slug, self.event.slug, self.order.code),
                             target_status_code=200)
        assert not self.ticket_pos.answers.filter(question=self.question).exists()

    def test_orders_questions_required(self):
        self.event.settings.set('attendee_names_asked', False)
        self.event.settings.set('attendee_names_required', False)
        self.question.required = True
        self.question.save()

        response = self.client.get('/%s/%s/order/%s/modify' % (self.orga.slug, self.event.slug, self.order.code))
        doc = BeautifulSoup(response.rendered_content)
        self.assertEqual(len(doc.select('input[name=%s-question_%s]' % (
            self.ticket_pos.identity, self.question.identity))), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/order/%s/modify' % (self.orga.slug, self.event.slug, self.order.code), {
            '%s-question_%s' % (self.ticket_pos.identity, self.question.identity): '',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        response = self.client.post('/%s/%s/order/%s/modify' % (self.orga.slug, self.event.slug, self.order.code), {
            '%s-question_%s' % (self.ticket_pos.identity, self.question.identity): 'ABC',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/order/%s/' % (self.orga.slug, self.event.slug, self.order.code),
                             target_status_code=200)
        assert self.ticket_pos.answers.get(question=self.question).answer == 'ABC'

    def test_orders_cancel_invalid(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        response = self.client.get(
            '/%s/%s/order/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code)
        )
        assert response.status_code == 403

    def test_orders_cancel(self):
        response = self.client.get(
            '/%s/%s/order/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code)
        )
        assert response.status_code == 200
        response = self.client.post('/%s/%s/order/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code), {
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/order/%s/' % (self.orga.slug, self.event.slug, self.order.code),
                             target_status_code=200)
        assert Order.objects.current.get(identity=self.order.identity).status == Order.STATUS_CANCELLED

    def test_orders_download(self):
        self.event.settings.set('ticket_download', True)
        del self.event.settings['ticket_download_date']
        response = self.client.get('/%s/%s/order/%s/download/pdf' % (self.orga.slug, self.event.slug, self.order.code),
                                   follow=True)
        self.assertRedirects(response, '/%s/%s/order/%s/' % (self.orga.slug, self.event.slug, self.order.code),
                             target_status_code=200)

        response = self.client.get(
            '/%s/%s/order/ABC/download/testdummy' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404

        response = self.client.get(
            '/%s/%s/order/%s/download/testdummy' % (self.orga.slug, self.event.slug, self.order.code),
            follow=True
        )
        self.assertRedirects(response, '/%s/%s/order/%s/' % (self.orga.slug, self.event.slug, self.order.code),
                             target_status_code=200)

        self.order.status = Order.STATUS_PAID
        self.order.save()
        response = self.client.get(
            '/%s/%s/order/%s/download/testdummy' % (self.orga.slug, self.event.slug, self.order.code),
        )
        assert response.status_code == 200
        assert response.content.strip().decode() == self.order.identity

        self.event.settings.set('ticket_download_date', now() + datetime.timedelta(days=1))
        response = self.client.get(
            '/%s/%s/order/%s/download/testdummy' % (self.orga.slug, self.event.slug, self.order.code),
            follow=True
        )
        self.assertRedirects(response, '/%s/%s/order/%s/' % (self.orga.slug, self.event.slug, self.order.code),
                             target_status_code=200)

        del self.event.settings['ticket_download_date']
        response = self.client.get(
            '/%s/%s/order/%s/download/testdummy' % (self.orga.slug, self.event.slug, self.order.code),
        )
        assert response.status_code == 200

        self.event.settings.set('ticket_download', False)
        response = self.client.get(
            '/%s/%s/order/%s/download/testdummy' % (self.orga.slug, self.event.slug, self.order.code),
            follow=True
        )
        self.assertRedirects(response, '/%s/%s/order/%s/' % (self.orga.slug, self.event.slug, self.order.code),
                             target_status_code=200)
