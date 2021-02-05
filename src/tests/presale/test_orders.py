import datetime
import re
from decimal import Decimal

from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, Item, ItemCategory, ItemVariation, Order, OrderPosition, Organizer,
    Question, Quota,
)
from pretix.base.models.orders import OrderFee, OrderPayment
from pretix.base.reldate import RelativeDate, RelativeDateWrapper
from pretix.base.services.invoices import generate_invoice


class BaseOrdersTest(TestCase):

    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.stripe,pretix.plugins.banktransfer,tests.testdummy',
            live=True
        )
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('ticketoutput_testdummy__enabled', True)

        self.category = ItemCategory.objects.create(event=self.event, name="Everything", position=0)
        self.quota_shirts = Quota.objects.create(event=self.event, name='Shirts', size=2)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', category=self.category, default_price=12)
        self.quota_shirts.items.add(self.shirt)
        self.shirt_red = ItemVariation.objects.create(item=self.shirt, default_price=14, value="Red")
        self.shirt_blue = ItemVariation.objects.create(item=self.shirt, value="Blue")
        self.quota_shirts.variations.add(self.shirt_red)
        self.quota_shirts.variations.add(self.shirt_blue)
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
            email='admin@localhost',
            datetime=now() - datetime.timedelta(days=3),
            expires=now() + datetime.timedelta(days=11),
            total=Decimal("23"),
            locale='en'
        )
        self.ticket_pos = OrderPosition.objects.create(
            order=self.order,
            item=self.ticket,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={'full_name': "Peter"}
        )
        self.deleted_pos = OrderPosition.objects.create(
            order=self.order,
            item=self.ticket,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={'full_name': "Lukas"},
            canceled=True
        )
        self.not_my_order = Order.objects.create(
            status=Order.STATUS_PENDING,
            event=self.event,
            email='user@localhost',
            datetime=now() - datetime.timedelta(days=3),
            expires=now() + datetime.timedelta(days=11),
            total=Decimal("23")
        )


class OrdersTest(BaseOrdersTest):
    def test_unknown_order(self):
        response = self.client.get(
            '/%s/%s/order/ABCDE/123/' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/%s/123/' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/ABCDE/123/pay' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/%s/123/pay' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/ABCDE/123/pay/confirm' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/%s/123/pay/confirm' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/ABCDE/123/modify' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/%s/123/modify' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/ABCDE/123/cancel' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/order/%s/123/cancel' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404
        response = self.client.post(
            '/%s/%s/order/ABCDE/123/cancel/do' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.post(
            '/%s/%s/order/%s/123/cancel/do' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404

    def test_unknown_position(self):
        response = self.client.get(
            '/%s/%s/ticket/ABCDE/1/123/' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/ticket/%s/1/123/' % (self.orga.slug, self.event.slug, self.order.code)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/ticket/%s/1/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/ticket/%s/1/123/' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404
        response = self.client.get(
            '/%s/%s/ticket/%s/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                         self.deleted_pos.positionid, self.deleted_pos.web_secret)
        )
        assert response.status_code == 404

    def test_orders_confirm_email(self):
        response = self.client.get(
            '/%s/%s/order/%s/%s/open/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret, 'aabbccdd')
        )
        assert response.status_code == 302
        self.order.refresh_from_db()
        assert not self.order.email_known_to_work

        response = self.client.get(
            '/%s/%s/order/%s/%s/open/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret, self.order.email_confirm_hash())
        )
        assert response.status_code == 302
        self.order.refresh_from_db()
        assert self.order.email_known_to_work

    def test_orders_detail(self):
        response = self.client.get(
            '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert len(doc.select(".cart-row")) > 0
        assert "pending" in doc.select(".label-warning")[0].text.lower()
        assert "Peter" in response.content.decode()
        assert "Lukas" not in response.content.decode()

    def test_ticket_detail(self):
        response = self.client.get(
            '/%s/%s/ticket/%s/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                         self.ticket_pos.positionid, self.ticket_pos.web_secret)
        )
        assert response.status_code == 200
        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert len(doc.select(".cart-row")) > 0
        assert "pending" in doc.select(".label-warning")[0].text.lower()
        assert "Peter" in response.content.decode()
        assert "Lukas" not in response.content.decode()

    def test_orders_modify_invalid(self):
        self.order.status = Order.STATUS_CANCELED
        self.order.save()
        self.client.get(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        with scopes_disabled():
            self.order = Order.objects.get(id=self.order.id)
            assert self.order.status == Order.STATUS_CANCELED

    def test_orders_modify_attendee_optional(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', False)

        response = self.client.get(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret))
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_0"]' % self.ticket_pos.id)), 1)

        # Not all fields filled out, expect success
        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-attendee_name_parts_0' % self.ticket_pos.id: '',
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        with scopes_disabled():
            self.ticket_pos = OrderPosition.objects.get(id=self.ticket_pos.id)
        assert self.ticket_pos.attendee_name in (None, '')

    def test_orders_modify_attendee_required(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', True)

        response = self.client.get(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret))
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_0"]' % self.ticket_pos.id)), 1)
        assert "Peter" in response.content.decode()
        assert "Lukas" not in response.content.decode()

        # Not all required fields filled out, expect failure
        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-attendee_name_parts_0' % self.ticket_pos.id: '',
            }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-attendee_name_parts_0' % self.ticket_pos.id: 'Peter',
            }, follow=True)
        self.assertRedirects(response, '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                                self.order.secret),
                             target_status_code=200)
        with scopes_disabled():
            self.ticket_pos = OrderPosition.objects.get(id=self.ticket_pos.id)
        assert self.ticket_pos.attendee_name == 'Peter'

    def test_orders_questions_optional(self):
        self.event.settings.set('attendee_names_asked', False)
        self.event.settings.set('attendee_names_required', False)

        response = self.client.get(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret))
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="%s-question_%s"]' % (
            self.ticket_pos.id, self.question.id))), 1)

        # Not all fields filled out, expect success
        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-question_%s' % (self.ticket_pos.id, self.question.id): '',
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        with scopes_disabled():
            assert not self.ticket_pos.answers.filter(question=self.question).exists()

    def test_orders_questions_required(self):
        self.event.settings.set('attendee_names_asked', False)
        self.event.settings.set('attendee_names_required', False)
        self.question.required = True
        self.question.save()

        response = self.client.get('/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code,
                                                                  self.order.secret))
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="%s-question_%s"]' % (
            self.ticket_pos.id, self.question.id))), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-question_%s' % (self.ticket_pos.id, self.question.id): '',
            }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-question_%s' % (self.ticket_pos.id, self.question.id): 'ABC',
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        with scopes_disabled():
            assert self.ticket_pos.answers.get(question=self.question).answer == 'ABC'

    def test_modify_invoice_regenerate(self):
        self.event.settings.set('invoice_reissue_after_modify', True)
        self.event.settings.set('invoice_address_asked', True)
        with scopes_disabled():
            generate_invoice(self.order)

        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-question_%s' % (self.ticket_pos.id, self.question.id): 'ABC',
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        # Only questions changed
        with scopes_disabled():
            assert self.order.invoices.count() == 1

        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-question_%s' % (self.ticket_pos.id, self.question.id): 'ABC',
                'zipcode': '1234',
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        with scopes_disabled():
            assert self.order.invoices.count() == 3

        self.event.settings.set('invoice_reissue_after_modify', False)

        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-question_%s' % (self.ticket_pos.id, self.question.id): 'ABC',
                'zipcode': '54321',
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        with scopes_disabled():
            assert self.order.invoices.count() == 3

    def test_orders_cancel_invalid(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        r = self.client.post(
            '/%s/%s/order/%s/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
            }, follow=True)
        assert 'btn-danger' not in r.content.decode()
        self.client.post(
            '/%s/%s/order/%s/%s/cancel/do' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
            }, follow=True)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID

    def test_orders_cancel(self):
        response = self.client.get(
            '/%s/%s/order/%s/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/cancel/do' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_CANCELED

    def test_orders_cancel_paid(self):
        self.event.settings.cancel_allow_user_paid = True
        response = self.client.get(
            '/%s/%s/order/%s/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/cancel/do' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_CANCELED

    def test_orders_cancel_paid_request(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        with scopes_disabled():
            self.order.payments.create(provider='testdummy_partialrefund', amount=self.order.total, state=OrderPayment.PAYMENT_STATE_CONFIRMED)
        self.event.settings.cancel_allow_user_paid = True
        self.event.settings.cancel_allow_user_paid_keep = Decimal('3.00')
        self.event.settings.cancel_allow_user_paid_require_approval = True
        response = self.client.get(
            '/%s/%s/order/%s/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/cancel/do' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID
        assert self.order.total == Decimal('23.00')
        with scopes_disabled():
            assert not self.order.refunds.exists()
            r = self.order.cancellation_requests.get()
            assert r.cancellation_fee == Decimal('3.00')

    def test_orders_cancel_paid_fee_autorefund_gift_card_optional(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        with scopes_disabled():
            self.order.payments.create(provider='testdummy_partialrefund', amount=self.order.total, state=OrderPayment.PAYMENT_STATE_CONFIRMED)
        self.event.settings.cancel_allow_user_paid = True
        self.event.settings.cancel_allow_user_paid_keep = Decimal('3.00')
        self.event.settings.cancel_allow_user_paid_refund_as_giftcard = 'option'
        response = self.client.get(
            '/%s/%s/order/%s/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'manually' not in response.content.decode()
        assert "gift card" in response.content.decode()
        response = self.client.post(
            '/%s/%s/order/%s/%s/cancel/do' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                'giftcard': 'true'
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        assert "gift card" in response.content.decode()
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID
        assert self.order.total == Decimal('3.00')
        with scopes_disabled():
            r = self.order.refunds.get()
            assert r.provider == "giftcard"
            assert r.amount == Decimal('20.00')

    def test_orders_cancel_paid_fee_autorefund_gift_card_force(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        with scopes_disabled():
            self.order.payments.create(provider='testdummy_partialrefund', amount=self.order.total, state=OrderPayment.PAYMENT_STATE_CONFIRMED)
        self.event.settings.cancel_allow_user_paid = True
        self.event.settings.cancel_allow_user_paid_keep = Decimal('3.00')
        self.event.settings.cancel_allow_user_paid_refund_as_giftcard = 'force'
        response = self.client.get(
            '/%s/%s/order/%s/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'manually' not in response.content.decode()
        assert "gift card" in response.content.decode()
        response = self.client.post(
            '/%s/%s/order/%s/%s/cancel/do' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                'giftcard': 'false'
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        assert "gift card" in response.content.decode()
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID
        assert self.order.total == Decimal('3.00')
        with scopes_disabled():
            r = self.order.refunds.get()
            assert r.provider == "giftcard"
            assert r.amount == Decimal('20.00')

    def test_orders_cancel_paid_fee_autorefund(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        with scopes_disabled():
            self.order.payments.create(provider='testdummy_partialrefund', amount=self.order.total, state=OrderPayment.PAYMENT_STATE_CONFIRMED)
        self.event.settings.cancel_allow_user_paid = True
        self.event.settings.cancel_allow_user_paid_keep = Decimal('3.00')
        response = self.client.get(
            '/%s/%s/order/%s/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'manually' not in response.content.decode()
        response = self.client.post(
            '/%s/%s/order/%s/%s/cancel/do' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID
        assert self.order.total == Decimal('3.00')
        with scopes_disabled():
            assert self.order.refunds.count() == 1

    def test_orders_cancel_paid_custom_fee_autorefund(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        with scopes_disabled():
            self.order.payments.create(provider='testdummy_partialrefund', amount=self.order.total, state=OrderPayment.PAYMENT_STATE_CONFIRMED)
        self.event.settings.cancel_allow_user_paid = True
        self.event.settings.cancel_allow_user_paid_keep = Decimal('3.00')
        self.event.settings.cancel_allow_user_paid_adjust_fees = True
        response = self.client.get(
            '/%s/%s/order/%s/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/cancel/do' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                'cancel_fee': '6.00'
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID
        assert self.order.total == Decimal('6.00')
        with scopes_disabled():
            assert self.order.refunds.count() == 1

    def test_orders_cancel_paid_custom_fee_limit(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        with scopes_disabled():
            self.order.payments.create(provider='testdummy_partialrefund', amount=self.order.total, state=OrderPayment.PAYMENT_STATE_CONFIRMED)
        self.event.settings.cancel_allow_user_paid = True
        self.event.settings.cancel_allow_user_paid_keep = Decimal('3.00')
        self.event.settings.cancel_allow_user_paid_adjust_fees = True
        response = self.client.get(
            '/%s/%s/order/%s/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/cancel/do' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                'cancel_fee': '2.00'
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID
        assert self.order.total == Decimal('23.00')
        with scopes_disabled():
            assert self.order.refunds.count() == 0

    def test_orders_cancel_paid_fee_no_autorefund(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        with scopes_disabled():
            self.order.payments.create(provider='testdummy', amount=self.order.total,
                                       state=OrderPayment.PAYMENT_STATE_CONFIRMED)
        self.event.settings.cancel_allow_user_paid = True
        self.event.settings.cancel_allow_user_paid_keep = Decimal('3.00')
        response = self.client.get(
            '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'cancellation fee of <strong>€3.00</strong>' in response.content.decode()
        response = self.client.get(
            '/%s/%s/order/%s/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'manually' in response.content.decode()
        assert '20.00' in response.content.decode()
        response = self.client.post(
            '/%s/%s/order/%s/%s/cancel/do' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID
        assert self.order.total == Decimal('3.00')
        with scopes_disabled():
            assert self.order.refunds.count() == 0

    def test_orders_cancel_forbidden(self):
        self.event.settings.set('cancel_allow_user', False)
        self.client.post(
            '/%s/%s/order/%s/%s/cancel/do' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
            }, follow=True)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PENDING

    def test_invoice_create_notallowed(self):
        self.event.settings.set('invoice_generate', 'no')
        response = self.client.post(
            '/%s/%s/order/%s/%s/invoice' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {}, follow=True)
        assert 'alert-danger' in response.content.decode()

    def test_invoice_create_duplicate(self):
        self.event.settings.set('invoice_generate', 'user')
        with scopes_disabled():
            generate_invoice(self.order)
        response = self.client.post(
            '/%s/%s/order/%s/%s/invoice' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {}, follow=True)
        assert 'alert-danger' in response.content.decode()

    def test_invoice_create_wrong_secret(self):
        self.event.settings.set('invoice_generate', 'user')
        with scopes_disabled():
            generate_invoice(self.order)
        response = self.client.post(
            '/%s/%s/order/%s/%s/invoice' % (self.orga.slug, self.event.slug, self.order.code, '1234'),
            {})
        assert 404 == response.status_code

    def test_invoice_create_require_payment(self):
        self.event.settings.set('invoice_generate', 'user')
        response = self.client.post(
            '/%s/%s/order/%s/%s/invoice' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {}, follow=True)
        assert 'alert-danger' in response.content.decode()
        with scopes_disabled():
            assert not self.order.invoices.exists()

    def test_invoice_create_ok(self):
        self.event.settings.set('invoice_generate', 'user')
        with scopes_disabled():
            self.order.payments.create(provider='banktransfer', state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                                       amount=self.order.total)
        response = self.client.post(
            '/%s/%s/order/%s/%s/invoice' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {}, follow=True)
        assert 'alert-success' in response.content.decode()
        with scopes_disabled():
            assert self.order.invoices.exists()

    def test_orders_download_pending(self):
        self.event.settings.set('ticket_download', True)
        del self.event.settings['ticket_download_date']

        self.order.status = Order.STATUS_PENDING
        self.order.save()
        self.event.settings.set('ticket_download_pending', True)
        response = self.client.post(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
            follow=True
        )
        assert response.status_code == 200

    def test_orders_download_pending_only_approved(self):
        self.event.settings.set('ticket_download', True)
        del self.event.settings['ticket_download_date']

        self.order.status = Order.STATUS_PENDING
        self.order.require_approval = True
        self.order.save()
        self.event.settings.set('ticket_download_pending', True)
        response = self.client.post(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)

    def test_ticket_download(self):
        self.event.settings.set('ticket_download', True)
        del self.event.settings['ticket_download_date']
        self.order.status = Order.STATUS_PAID
        self.order.save()
        response = self.client.post(
            '/%s/%s/ticket/%s/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                              self.ticket_pos.positionid, self.ticket_pos.web_secret,
                                                              self.ticket_pos.pk),
            follow=True)
        assert response.status_code == 200

    def test_orders_download(self):
        self.event.settings.set('ticket_download', True)
        del self.event.settings['ticket_download_date']
        response = self.client.post(
            '/%s/%s/order/%s/%s/download/%d/pdf' % (self.orga.slug, self.event.slug, self.order.code,
                                                    self.order.secret, self.ticket_pos.pk),
            follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)

        response = self.client.post(
            '/%s/%s/order/ABC/123/download/%d/testdummy' % (self.orga.slug, self.event.slug,
                                                            self.ticket_pos.pk)
        )
        assert response.status_code == 404

        response = self.client.post(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
            follow=True
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)

        self.order.status = Order.STATUS_PAID
        self.order.save()
        response = self.client.post(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
            follow=True
        )
        assert response.status_code == 200

        self.event.settings.set('ticket_download_date', now() + datetime.timedelta(days=1))
        response = self.client.post(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
            follow=True
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)

        self.event.date_from = now() + datetime.timedelta(days=3)
        self.event.save()
        self.event.settings.set('ticket_download_date', RelativeDateWrapper(RelativeDate(
            base_date_name='date_from', days_before=2, time=None, minutes_before=None
        )))
        response = self.client.post(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
            follow=True
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)

        del self.event.settings['ticket_download_date']
        response = self.client.post(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
            follow=True
        )
        assert response.status_code == 200

        self.event.settings.set('ticket_download', False)
        response = self.client.post(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
            follow=True
        )
        self.assertRedirects(response, '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                                self.order.secret),
                             target_status_code=200)

    def test_change_paymentmethod_wrong_secret(self):
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, '123'))
        assert response.status_code == 404

    def test_change_paymentmethod_wrong_state(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            follow=True
        )
        assert 'alert-danger' in response.content.decode()

    def test_pay_wrong_payment_state(self):
        with scopes_disabled():
            p = self.order.payments.create(
                provider='manual',
                state=OrderPayment.PAYMENT_STATE_CANCELED,
                amount=Decimal('10.00'),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/%d/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret,
                                            p.pk),
            follow=True
        )
        assert 'alert-danger' in response.content.decode()
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/%d/confirm' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret,
                                                   p.pk),
            follow=True
        )
        assert 'alert-danger' in response.content.decode()
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/%d/complete' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret,
                                                    p.pk),
            follow=True
        )
        assert 'alert-danger' in response.content.decode()

    def test_pay_wrong_order_state(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        with scopes_disabled():
            p = self.order.payments.create(
                provider='manual',
                state=OrderPayment.PAYMENT_STATE_PENDING,
                amount=Decimal('10.00'),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/%d/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret,
                                            p.pk),
            follow=True
        )
        assert 'alert-danger' in response.content.decode()
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/%d/confirm' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret,
                                                   p.pk),
            follow=True
        )
        assert 'alert-danger' in response.content.decode()
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/%d/complete' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret,
                                                    p.pk),
            follow=True
        )
        assert 'alert-danger' in response.content.decode()

    def test_pay_change_link(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        with scopes_disabled():
            p = self.order.payments.create(
                provider='banktransfer',
                state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                amount=self.order.total,
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            follow=True
        )
        assert '/pay/change' not in response.content.decode()
        self.order.status = Order.STATUS_PENDING
        self.order.save()
        p.state = OrderPayment.PAYMENT_STATE_PENDING
        p.save()
        response = self.client.get(
            '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            follow=True
        )
        assert '/pay/change' in response.content.decode()
        p.provider = 'testdummy'
        p.save()
        response = self.client.get(
            '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            follow=True
        )
        assert '/pay/change' not in response.content.decode()

    def test_change_paymentmethod_partial(self):
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('payment_testdummy__enabled', True)
        self.event.settings.set('payment_testdummy__fee_reverse_calc', False)
        self.event.settings.set('payment_testdummy__fee_percent', '10.00')
        with scopes_disabled():
            self.order.payments.create(
                provider='manual',
                state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                amount=Decimal('10.00'),
            )

            generate_invoice(self.order)
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
        )
        assert 'Test dummy' in response.content.decode()
        assert '+ €1.30' in response.content.decode()
        self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'testdummy'
            }
        )
        self.order.refresh_from_db()
        with scopes_disabled():
            assert self.order.payments.last().provider == 'testdummy'
            fee = self.order.fees.filter(fee_type=OrderFee.FEE_TYPE_PAYMENT).last()
            assert fee.value == Decimal('1.30')
            assert self.order.total == Decimal('23.00') + fee.value
            assert self.order.invoices.count() == 3
            p = self.order.payments.last()
            assert p.provider == 'testdummy'
            assert p.state == OrderPayment.PAYMENT_STATE_CREATED
            assert p.amount == Decimal('14.30')

    def test_change_paymentmethod_partial_with_previous_fee(self):
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('payment_testdummy__enabled', True)
        self.event.settings.set('payment_testdummy__fee_reverse_calc', False)
        self.event.settings.set('payment_testdummy__fee_percent', '10.00')
        with scopes_disabled():
            f = self.order.fees.create(
                fee_type=OrderFee.FEE_TYPE_PAYMENT,
                value='1.40'
            )
            self.order.total += Decimal('1.4')
            self.order.save()
            self.order.payments.create(
                provider='manual',
                state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                amount=Decimal('11.40'),
                fee=f
            )

            generate_invoice(self.order)
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
        )
        assert 'Test dummy' in response.content.decode()
        assert '+ €1.30' in response.content.decode()
        self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'testdummy'
            }
        )
        self.order.refresh_from_db()
        with scopes_disabled():
            assert self.order.payments.last().provider == 'testdummy'
            fee = self.order.fees.filter(fee_type=OrderFee.FEE_TYPE_PAYMENT).last()
            assert fee.value == Decimal('1.30')
            assert self.order.total == Decimal('24.40') + fee.value
            assert self.order.invoices.count() == 3
            p = self.order.payments.last()
        assert p.provider == 'testdummy'
        assert p.state == OrderPayment.PAYMENT_STATE_CREATED
        assert p.amount == Decimal('14.30')
        self.client.get(
            '/%s/%s/order/%s/%s/pay/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                            self.order.secret, p.pk),
            {}
        )
        self.client.get(
            '/%s/%s/order/%s/%s/pay/%s/confirm' % (self.orga.slug, self.event.slug, self.order.code,
                                                   self.order.secret, p.pk),
            {}
        )
        p.refresh_from_db()
        assert p.state == OrderPayment.PAYMENT_STATE_CREATED

    def test_change_paymentmethod_to_same(self):
        with scopes_disabled():
            p_old = self.order.payments.create(
                provider='banktransfer',
                state=OrderPayment.PAYMENT_STATE_CREATED,
                amount=Decimal('10.00'),
            )
        self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'banktransfer'
            }
        )
        self.order.refresh_from_db()
        with scopes_disabled():
            p_new = self.order.payments.last()
        assert p_new.provider == 'banktransfer'
        assert p_new.id != p_old.id
        assert p_new.state == OrderPayment.PAYMENT_STATE_CREATED
        p_old.refresh_from_db()
        assert p_old.state == OrderPayment.PAYMENT_STATE_CANCELED

    def test_change_paymentmethod_cancel_old(self):
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            p_old = self.order.payments.create(
                provider='testdummy',
                state=OrderPayment.PAYMENT_STATE_CREATED,
                amount=Decimal('10.00'),
            )
        self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'banktransfer'
            }
        )
        self.order.refresh_from_db()
        with scopes_disabled():
            p_new = self.order.payments.last()
            assert p_new.provider == 'banktransfer'
            assert p_new.id != p_old.id
            assert p_new.state == OrderPayment.PAYMENT_STATE_CREATED
            p_old.refresh_from_db()
            assert p_old.state == OrderPayment.PAYMENT_STATE_CANCELED

    def test_change_paymentmethod_delete_fee(self):
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('payment_testdummy__enabled', True)
        self.event.settings.set('payment_testdummy__fee_reverse_calc', False)
        self.event.settings.set('payment_testdummy__fee_percent', '0.00')
        with scopes_disabled():
            f = self.order.fees.create(
                fee_type=OrderFee.FEE_TYPE_PAYMENT,
                value='1.40'
            )
            self.order.total += Decimal('1.4')
            self.order.save()
            p0 = self.order.payments.create(
                provider='manual',
                state=OrderPayment.PAYMENT_STATE_CREATED,
                amount=Decimal('24.40'),
                fee=f
            )

            generate_invoice(self.order)
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
        )
        assert 'Test dummy' in response.content.decode()
        assert '- €1.40' in response.content.decode()
        self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'testdummy'
            }
        )
        with scopes_disabled():
            self.order.refresh_from_db()
            assert self.order.payments.last().provider == 'testdummy'
            assert not self.order.fees.filter(fee_type=OrderFee.FEE_TYPE_PAYMENT).exists()
            assert self.order.total == Decimal('23.00')
            assert self.order.invoices.count() == 3
            p0.refresh_from_db()
            assert p0.state == OrderPayment.PAYMENT_STATE_CANCELED
            p = self.order.payments.last()
            assert p.provider == 'testdummy'
            assert p.state == OrderPayment.PAYMENT_STATE_CREATED
            assert p.amount == Decimal('23.00')

    def test_change_paymentmethod_available(self):
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('payment_testdummy__enabled', True)
        self.event.settings.set('payment_testdummy__fee_abs', '12.00')
        with scopes_disabled():
            generate_invoice(self.order)
            self.order.payments.create(
                provider='banktransfer',
                state=OrderPayment.PAYMENT_STATE_PENDING,
                amount=self.order.total,
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
        )
        assert 'Test dummy' in response.content.decode()
        assert '+ €12.00' in response.content.decode()
        self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'testdummy'
            }
        )
        self.order.refresh_from_db()
        with scopes_disabled():
            p = self.order.payments.last()
            assert p.provider == 'testdummy'
            assert p.state == OrderPayment.PAYMENT_STATE_CREATED
            p0 = self.order.payments.first()
            assert p0.state == OrderPayment.PAYMENT_STATE_CANCELED
            assert p0.provider == 'banktransfer'
            fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
            assert fee.value == Decimal('12.00')
            assert self.order.total == Decimal('23.00') + fee.value
            assert self.order.invoices.count() == 3

    def test_change_paymentmethod_giftcard_partial(self):
        with scopes_disabled():
            self.order.payments.create(
                provider='manual',
                state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                amount=Decimal('10.00'),
            )
            gc = self.orga.issued_gift_cards.create(currency="EUR")
            gc.transactions.create(value=10)
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
        )
        assert 'Gift card' in response.content.decode()
        response = self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'giftcard',
                'giftcard': gc.secret
            }
        )
        with scopes_disabled():
            p = self.order.payments.last()
        self.assertRedirects(
            response,
            '/%s/%s/order/%s/%s/pay/%s/confirm' % (self.orga.slug, self.event.slug, self.order.code,
                                                   self.order.secret, p.pk),
        )
        self.client.post(
            '/%s/%s/order/%s/%s/pay/%s/confirm' % (self.orga.slug, self.event.slug, self.order.code,
                                                   self.order.secret, p.pk),
            {}
        )
        self.order.refresh_from_db()
        p.refresh_from_db()
        assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
        assert self.order.status == Order.STATUS_PENDING
        assert gc.value == Decimal('0.00')
        assert self.order.pending_sum == Decimal('3.00')

    def test_change_paymentmethod_giftcard_swap_card(self):
        with scopes_disabled():
            self.order.payments.create(
                provider='manual',
                state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                amount=Decimal('10.00'),
            )
            gc = self.orga.issued_gift_cards.create(currency="EUR")
            gc.transactions.create(value=10)
            self.ticket.issue_giftcard = True
            self.ticket.save()
        response = self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'giftcard',
                'giftcard': gc.secret
            }
        )
        assert "You cannot pay with gift cards when buying a gift card." in response.content.decode()

    def test_change_paymentmethod_giftcard_wrong_currency(self):
        with scopes_disabled():
            gc = self.orga.issued_gift_cards.create(currency="USD")
            gc.transactions.create(value=10)
        response = self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'giftcard',
                'giftcard': gc.secret
            }
        )
        assert "This gift card does not support this currency." in response.content.decode()

    def test_change_paymentmethod_giftcard_in_test_mode(self):
        with scopes_disabled():
            self.order.testmode = True
            self.order.save()
            gc = self.orga.issued_gift_cards.create(currency="EUR")
            gc.transactions.create(value=10)
        response = self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'giftcard',
                'giftcard': gc.secret
            }
        )
        assert "Only test gift cards can be used in test mode." in response.content.decode()

    def test_change_paymentmethod_giftcard_not_in_test_mode(self):
        with scopes_disabled():
            gc = self.orga.issued_gift_cards.create(currency="EUR", testmode=True)
            gc.transactions.create(value=10)
        response = self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'giftcard',
                'giftcard': gc.secret
            }
        )
        assert "This gift card can only be used in test mode." in response.content.decode()

    def test_change_paymentmethod_giftcard_empty(self):
        with scopes_disabled():
            gc = self.orga.issued_gift_cards.create(currency="EUR")
        response = self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'giftcard',
                'giftcard': gc.secret
            }
        )
        assert "All credit on this gift card has been used." in response.content.decode()

    def test_change_paymentmethod_giftcard_wrong_organizer(self):
        with scopes_disabled():
            o = Organizer.objects.create(slug='Foo', name='bar')
            self.orga.issued_gift_cards.create(currency="EUR")
            gc = o.issued_gift_cards.create(currency="EUR")
            gc.transactions.create(value=10)
        response = self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'giftcard',
                'giftcard': gc.secret
            }
        )
        assert "This gift card is not known." in response.content.decode()

    def test_change_paymentmethod_giftcard(self):
        with scopes_disabled():
            self.order.payments.create(
                provider='manual',
                state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                amount=Decimal('10.00'),
            )
            gc = self.orga.issued_gift_cards.create(currency="EUR")
            gc.transactions.create(value=100)
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
        )
        assert 'Gift card' in response.content.decode()
        response = self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'giftcard',
                'giftcard': gc.secret
            }
        )
        with scopes_disabled():
            p = self.order.payments.last()
        self.assertRedirects(
            response,
            '/%s/%s/order/%s/%s/pay/%s/confirm' % (self.orga.slug, self.event.slug, self.order.code,
                                                   self.order.secret, p.pk),
        )
        self.client.post(
            '/%s/%s/order/%s/%s/pay/%s/confirm' % (self.orga.slug, self.event.slug, self.order.code,
                                                   self.order.secret, p.pk),
            {}
        )
        self.order.refresh_from_db()
        p.refresh_from_db()
        assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
        assert self.order.status == Order.STATUS_PAID
        assert gc.value == Decimal('87.00')

    def test_answer_download_token(self):
        with scopes_disabled():
            q = self.event.questions.create(question="Foo", type="F")
            q.items.add(self.ticket)
            a = self.ticket_pos.answers.create(question=q, answer="file")
            val = SimpleUploadedFile("testfile.txt", b"file_content")
            a.file.save("testfile.txt", val)
            a.save()

        self.event.settings.set('ticket_download', True)
        del self.event.settings['ticket_download_date']
        response = self.client.get(
            '/%s/%s/order/%s/%s/answer/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                               self.order.secret, a.pk)
        )
        assert response.status_code == 404

        response = self.client.get(
            '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        match = re.search(r"\?token=([^'\"&]+)", response.content.decode())
        assert match

        response = self.client.get(
            '/%s/%s/order/%s/%s/answer/%s/?token=%s' % (self.orga.slug, self.event.slug, self.order.code,
                                                        self.order.secret, a.pk, match.group(1))
        )
        assert response.status_code == 200

        client2 = self.client_class()
        response = client2.get(
            '/%s/%s/order/%s/%s/answer/%s/?token=%s' % (self.orga.slug, self.event.slug, self.order.code,
                                                        self.order.secret, a.pk, match.group(1))
        )
        assert response.status_code == 404

    def test_change_not_allowed(self):
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 302

    def test_change_variation_paid(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'any'

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_red,
                price=Decimal("14"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_blue.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        shirt_pos.refresh_from_db()
        assert shirt_pos.variation == self.shirt_blue
        assert shirt_pos.price == Decimal('12.00')
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PENDING
        assert self.order.total == Decimal('35.00')

    def test_change_variation_require_higher_price(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'gt'

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_red,
                price=Decimal("14"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_blue.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        assert 'alert-danger' in response.content.decode()

        shirt_pos.variation = self.shirt_blue
        shirt_pos.price = Decimal('12.00')
        shirt_pos.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            },
            follow=True
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        shirt_pos.refresh_from_db()
        assert shirt_pos.variation == self.shirt_red
        assert shirt_pos.price == Decimal('14.00')
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PENDING
        assert self.order.total == Decimal('37.00')

        shirt_pos.variation = self.shirt_blue
        shirt_pos.price = Decimal('14.00')
        shirt_pos.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            },
            follow=True
        )
        shirt_pos.refresh_from_db()
        assert 'alert-danger' in response.content.decode()
        assert shirt_pos.variation == self.shirt_blue
        assert shirt_pos.price == Decimal('14.00')

    def test_change_variation_require_higher_equal_price(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'gte'

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_red,
                price=Decimal("14"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_blue.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        assert 'alert-danger' in response.content.decode()

        shirt_pos.variation = self.shirt_blue
        shirt_pos.price = Decimal('12.00')
        shirt_pos.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            },
            follow=True
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        shirt_pos.refresh_from_db()
        assert shirt_pos.variation == self.shirt_red
        assert shirt_pos.price == Decimal('14.00')
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PENDING
        assert self.order.total == Decimal('37.00')

        shirt_pos.variation = self.shirt_blue
        shirt_pos.price = Decimal('14.00')
        shirt_pos.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            },
            follow=True
        )
        shirt_pos.refresh_from_db()
        assert 'alert-success' in response.content.decode()
        assert shirt_pos.variation == self.shirt_red
        assert shirt_pos.price == Decimal('14.00')

    def test_change_variation_require_equal_price(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'eq'

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_blue,
                price=Decimal("12"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        assert 'alert-danger' in response.content.decode()

    def test_change_variation_require_same_product(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'any'

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_blue,
                price=Decimal("12"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.ticket.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        assert 'alert-danger' in response.content.decode()

    def test_change_variation_require_quota(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'any'

        with scopes_disabled():
            q = self.event.quotas.create(name="s2", size=0)
            q.items.add(self.shirt)
            q.variations.add(self.shirt_red)

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_blue,
                price=Decimal("12"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        assert 'alert-danger' in response.content.decode()

        q.variations.add(self.shirt_blue)

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        shirt_pos.refresh_from_db()
        assert shirt_pos.variation == self.shirt_red
        assert shirt_pos.price == Decimal('14.00')

    def test_change_paid_to_pending(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'any'
        self.order.status = Order.STATUS_PAID
        self.order.save()

        with scopes_disabled():
            self.order.payments.create(provider="manual", amount=Decimal('35.00'), state=OrderPayment.PAYMENT_STATE_CONFIRMED)
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_blue,
                price=Decimal("12"),
            )

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            },
            follow=True
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code,
                                                                self.order.secret),
                             target_status_code=200)
        assert 'The order has been changed. You can now proceed by paying the open amount of €2.00.' in response.content.decode()
        shirt_pos.refresh_from_db()
        assert shirt_pos.variation == self.shirt_red
        assert shirt_pos.price == Decimal('14.00')
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PENDING
        assert self.order.pending_sum == Decimal('2.00')
