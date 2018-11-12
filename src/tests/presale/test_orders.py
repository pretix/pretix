import datetime
import re
from decimal import Decimal

from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import (
    Event, Item, ItemCategory, ItemVariation, Order, OrderPosition, Organizer,
    Question, Quota,
)
from pretix.base.models.orders import OrderFee, OrderPayment
from pretix.base.reldate import RelativeDate, RelativeDateWrapper
from pretix.base.services.invoices import generate_invoice


class OrdersTest(TestCase):
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
        var2 = ItemVariation.objects.create(item=self.shirt, value="Blue")
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
        self.not_my_order = Order.objects.create(
            status=Order.STATUS_PENDING,
            event=self.event,
            email='user@localhost',
            datetime=now() - datetime.timedelta(days=3),
            expires=now() + datetime.timedelta(days=11),
            total=Decimal("23")
        )

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

    def test_orders_detail(self):
        response = self.client.get(
            '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        doc = BeautifulSoup(response.rendered_content, "lxml")
        assert len(doc.select(".cart-row")) > 0
        assert "pending" in doc.select(".label-warning")[0].text.lower()

    def test_orders_modify_invalid(self):
        self.order.status = Order.STATUS_REFUNDED
        self.order.save()
        self.client.get(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        self.order = Order.objects.get(id=self.order.id)
        assert self.order.status == Order.STATUS_REFUNDED

    def test_orders_modify_attendee_optional(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', False)

        response = self.client.get(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret))
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name=%s-attendee_name_parts_0]' % self.ticket_pos.id)), 1)

        # Not all fields filled out, expect success
        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-attendee_name_parts_0' % self.ticket_pos.id: '',
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        self.ticket_pos = OrderPosition.objects.get(id=self.ticket_pos.id)
        assert self.ticket_pos.attendee_name in (None, '')

    def test_orders_modify_attendee_required(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', True)

        response = self.client.get(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret))
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name=%s-attendee_name_parts_0]' % self.ticket_pos.id)), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-attendee_name_parts_0' % self.ticket_pos.id: '',
            }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-attendee_name_parts_0' % self.ticket_pos.id: 'Peter',
            }, follow=True)
        self.assertRedirects(response, '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                                self.order.secret),
                             target_status_code=200)
        self.ticket_pos = OrderPosition.objects.get(id=self.ticket_pos.id)
        assert self.ticket_pos.attendee_name == 'Peter'

    def test_orders_questions_optional(self):
        self.event.settings.set('attendee_names_asked', False)
        self.event.settings.set('attendee_names_required', False)

        response = self.client.get(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret))
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name=%s-question_%s]' % (
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
        assert not self.ticket_pos.answers.filter(question=self.question).exists()

    def test_orders_questions_required(self):
        self.event.settings.set('attendee_names_asked', False)
        self.event.settings.set('attendee_names_required', False)
        self.question.required = True
        self.question.save()

        response = self.client.get('/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code,
                                                                  self.order.secret))
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertEqual(len(doc.select('input[name=%s-question_%s]' % (
            self.ticket_pos.id, self.question.id))), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-question_%s' % (self.ticket_pos.id, self.question.id): '',
            }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        response = self.client.post(
            '/%s/%s/order/%s/%s/modify' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                '%s-question_%s' % (self.ticket_pos.id, self.question.id): 'ABC',
            }, follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        assert self.ticket_pos.answers.get(question=self.question).answer == 'ABC'

    def test_orders_cancel_invalid(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        r = self.client.post(
            '/%s/%s/order/%s/%s/cancel' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
            }, follow=True)
        assert 'btn-danger' not in r.rendered_content
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
        assert 'alert-danger' in response.rendered_content

    def test_invoice_create_duplicate(self):
        self.event.settings.set('invoice_generate', 'user')
        generate_invoice(self.order)
        response = self.client.post(
            '/%s/%s/order/%s/%s/invoice' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {}, follow=True)
        assert 'alert-danger' in response.rendered_content

    def test_invoice_create_wrong_secret(self):
        self.event.settings.set('invoice_generate', 'user')
        generate_invoice(self.order)
        response = self.client.post(
            '/%s/%s/order/%s/%s/invoice' % (self.orga.slug, self.event.slug, self.order.code, '1234'),
            {})
        assert 404 == response.status_code

    def test_invoice_create_ok(self):
        self.event.settings.set('invoice_generate', 'user')
        response = self.client.post(
            '/%s/%s/order/%s/%s/invoice' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {}, follow=True)
        assert 'alert-success' in response.rendered_content
        assert self.order.invoices.exists()

    def test_orders_download_pending(self):
        self.event.settings.set('ticket_download', True)
        del self.event.settings['ticket_download_date']

        self.order.status = Order.STATUS_PENDING
        self.order.save()
        self.event.settings.set('ticket_download_pending', True)
        response = self.client.get(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
        )
        assert response.status_code == 200

    def test_orders_download_pending_only_approved(self):
        self.event.settings.set('ticket_download', True)
        del self.event.settings['ticket_download_date']

        self.order.status = Order.STATUS_PENDING
        self.order.require_approval = True
        self.order.save()
        self.event.settings.set('ticket_download_pending', True)
        response = self.client.get(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)

    def test_orders_download(self):
        self.event.settings.set('ticket_download', True)
        del self.event.settings['ticket_download_date']
        response = self.client.get(
            '/%s/%s/order/%s/%s/download/%d/pdf' % (self.orga.slug, self.event.slug, self.order.code,
                                                    self.order.secret, self.ticket_pos.pk),
            follow=True)
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)

        response = self.client.get(
            '/%s/%s/order/ABC/123/download/%d/testdummy' % (self.orga.slug, self.event.slug,
                                                            self.ticket_pos.pk)
        )
        assert response.status_code == 404

        response = self.client.get(
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
        response = self.client.get(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
        )
        assert response.status_code == 200

        self.event.settings.set('ticket_download_date', now() + datetime.timedelta(days=1))
        response = self.client.get(
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
            base_date_name='date_from', days_before=2, time=None
        )))
        response = self.client.get(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
            follow=True
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)

        del self.event.settings['ticket_download_date']
        response = self.client.get(
            '/%s/%s/order/%s/%s/download/%d/testdummy' % (self.orga.slug, self.event.slug, self.order.code,
                                                          self.order.secret, self.ticket_pos.pk),
        )
        assert response.status_code == 200

        self.event.settings.set('ticket_download', False)
        response = self.client.get(
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
        assert 'alert-danger' in response.rendered_content

    def test_pay_wrong_payment_state(self):
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
        assert 'alert-danger' in response.rendered_content
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/%d/confirm' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret,
                                                   p.pk),
            follow=True
        )
        assert 'alert-danger' in response.rendered_content
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/%d/complete' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret,
                                                    p.pk),
            follow=True
        )
        assert 'alert-danger' in response.rendered_content

    def test_pay_wrong_order_state(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
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
        assert 'alert-danger' in response.rendered_content
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/%d/confirm' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret,
                                                   p.pk),
            follow=True
        )
        assert 'alert-danger' in response.rendered_content
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/%d/complete' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret,
                                                    p.pk),
            follow=True
        )
        assert 'alert-danger' in response.rendered_content

    def test_pay_change_link(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        p = self.order.payments.create(
            provider='banktransfer',
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            amount=self.order.total,
        )
        response = self.client.get(
            '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            follow=True
        )
        assert '/pay/change' not in response.rendered_content
        self.order.status = Order.STATUS_PENDING
        self.order.save()
        p.state = OrderPayment.PAYMENT_STATE_PENDING
        p.save()
        response = self.client.get(
            '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            follow=True
        )
        assert '/pay/change' in response.rendered_content
        p.provider = 'testdummy'
        p.save()
        response = self.client.get(
            '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            follow=True
        )
        assert '/pay/change' not in response.rendered_content

    def test_change_paymentmethod_partial(self):
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('payment_testdummy__enabled', True)
        self.event.settings.set('payment_testdummy__fee_reverse_calc', False)
        self.event.settings.set('payment_testdummy__fee_percent', '10.00')
        self.order.payments.create(
            provider='manual',
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            amount=Decimal('10.00'),
        )

        generate_invoice(self.order)
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
        )
        assert 'Test dummy' in response.rendered_content
        assert '+ €1.30' in response.rendered_content
        self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'testdummy'
            }
        )
        self.order.refresh_from_db()
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
        assert 'Test dummy' in response.rendered_content
        assert '+ €1.30' in response.rendered_content
        self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'testdummy'
            }
        )
        self.order.refresh_from_db()
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

    def test_change_paymentmethod_delete_fee(self):
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('payment_testdummy__enabled', True)
        self.event.settings.set('payment_testdummy__fee_reverse_calc', False)
        self.event.settings.set('payment_testdummy__fee_percent', '0.00')
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
        assert 'Test dummy' in response.rendered_content
        assert '- €1.40' in response.rendered_content
        self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'testdummy'
            }
        )
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
        generate_invoice(self.order)
        self.order.payments.create(
            provider='banktransfer',
            state=OrderPayment.PAYMENT_STATE_PENDING,
            amount=self.order.total,
        )
        response = self.client.get(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
        )
        assert 'Test dummy' in response.rendered_content
        assert '+ €12.00' in response.rendered_content
        response = self.client.post(
            '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'payment': 'testdummy'
            }
        )
        self.order.refresh_from_db()
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

    def test_answer_download_token(self):
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
        match = re.search(r"\?token=([^'\"&]+)", response.rendered_content)
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
