from datetime import timedelta
from decimal import Decimal

from django.core import mail as djmail
from django.test import TestCase
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import (
    Event, Item, Order, OrderPosition, Organizer, Voucher, WaitingListEntry,
)
from pretix.base.models.orders import OrderFee, OrderPayment, OrderRefund
from pretix.base.services.cancelevent import cancel_event
from pretix.base.services.invoices import generate_invoice
from pretix.testutils.scope import classscope


class EventCancelTests(TestCase):
    def setUp(self):
        super().setUp()
        self.o = Organizer.objects.create(name='Dummy', slug='dummy')
        with scope(organizer=self.o):
            self.event = Event.objects.create(organizer=self.o, name='Dummy', slug='dummy', date_from=now(),
                                              plugins='tests.testdummy')
            self.order = Order.objects.create(
                code='FOO', event=self.event, email='dummy@dummy.test',
                status=Order.STATUS_PENDING, locale='en',
                datetime=now(), expires=now() + timedelta(days=10),
                total=Decimal('46.00'),
            )
            self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                              default_price=Decimal('23.00'), admission=True)
            self.op1 = OrderPosition.objects.create(
                order=self.order, item=self.ticket, variation=None,
                price=Decimal("23.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
            )
            self.op2 = OrderPosition.objects.create(
                order=self.order, item=self.ticket, variation=None,
                price=Decimal("23.00"), attendee_name_parts={'full_name': "Dieter"}, positionid=2
            )
            generate_invoice(self.order)
            djmail.outbox = []

    @classscope(attr='o')
    def test_cancel_send_mail(self):
        gc = self.o.issued_gift_cards.create(currency="EUR")
        self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='giftcard',
            info='{"gift_card": %d}' % gc.pk
        )
        self.order.status = Order.STATUS_PAID
        self.order.save()
        cancel_event(
            self.event.pk, subevent=None,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="0.00",
            send=True, send_subject="Event canceled", send_message="Event canceled :-( {refund_amount}",
            user=None
        )
        assert len(djmail.outbox) == 1
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_CANCELED
        assert '46.00' in djmail.outbox[0].body

    @classscope(attr='o')
    def test_cancel_send_mail_attendees(self):
        self.op1.attendee_email = 'foo@example.com'
        self.op1.save()
        cancel_event(
            self.event.pk, subevent=None,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="0.00",
            send=True, send_subject="Event canceled", send_message="Event canceled :-(",
            user=None
        )
        assert len(djmail.outbox) == 2
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_CANCELED

    @classscope(attr='o')
    def test_cancel_auto_refund(self):
        gc = self.o.issued_gift_cards.create(currency="EUR")
        p1 = self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='giftcard',
            info='{"gift_card": %d}' % gc.pk
        )
        self.order.status = Order.STATUS_PAID
        self.order.save()

        cancel_event(
            self.event.pk, subevent=None,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="0.00",
            send=True, send_subject="Event canceled", send_message="Event canceled :-(",
            user=None
        )

        r = self.order.refunds.get()
        assert r.state == OrderRefund.REFUND_STATE_DONE
        assert r.amount == Decimal('46.00')
        assert r.source == OrderRefund.REFUND_SOURCE_ADMIN
        assert r.payment == p1
        assert self.order.all_logentries().filter(action_type='pretix.event.order.refund.created').exists()
        assert not self.order.all_logentries().filter(action_type='pretix.event.order.refund.requested').exists()
        assert gc.value == Decimal('46.00')

    @classscope(attr='o')
    def test_cancel_do_not_refund(self):
        gc = self.o.issued_gift_cards.create(currency="EUR")
        self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='giftcard',
            info='{"gift_card": %d}' % gc.pk
        )
        self.order.status = Order.STATUS_PAID
        self.order.save()

        cancel_event(
            self.event.pk, subevent=None,
            auto_refund=False, keep_fee_fixed="0.00", keep_fee_percentage="0.00",
            send=True, send_subject="Event canceled", send_message="Event canceled :-(",
            user=None
        )

        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_CANCELED
        assert not self.order.refunds.exists()

    @classscope(attr='o')
    def test_cancel_refund_paid_with_fees(self):
        gc = self.o.issued_gift_cards.create(currency="EUR")
        p1 = self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='giftcard',
            info='{"gift_card": %d}' % gc.pk
        )
        self.order.status = Order.STATUS_PAID
        self.order.save()

        cancel_event(
            self.event.pk, subevent=None,
            auto_refund=True, keep_fee_fixed="10.00", keep_fee_percentage="10.00",
            send=False, send_subject="Event canceled", send_message="Event canceled :-(",
            user=None
        )

        r = self.order.refunds.get()
        assert r.state == OrderRefund.REFUND_STATE_DONE
        assert r.amount == Decimal('31.40')
        assert r.source == OrderRefund.REFUND_SOURCE_ADMIN
        assert r.payment == p1
        assert self.order.all_logentries().filter(action_type='pretix.event.order.refund.created').exists()
        assert not self.order.all_logentries().filter(action_type='pretix.event.order.refund.requested').exists()
        assert gc.value == Decimal('31.40')

    @classscope(attr='o')
    def test_cancel_refund_partially_paid_with_fees(self):
        gc = self.o.issued_gift_cards.create(currency="EUR")
        self.order.payments.create(
            amount=Decimal('12.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='giftcard',
            info='{"gift_card": %d}' % gc.pk
        )
        self.order.status = Order.STATUS_PENDING
        self.order.save()

        cancel_event(
            self.event.pk, subevent=None,
            auto_refund=True, keep_fee_fixed="10.00", keep_fee_percentage="10.00",
            send=False, send_subject="Event canceled", send_message="Event canceled :-(",
            user=None
        )

        assert not self.order.refunds.exists()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('12.00')
        assert self.order.status == Order.STATUS_PAID
        assert self.order.positions.count() == 0

    @classscope(attr='o')
    def test_cancel_keep_fees(self):
        gc = self.o.issued_gift_cards.create(currency="EUR")
        p1 = self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='giftcard',
            info='{"gift_card": %d}' % gc.pk
        )
        self.op1.price -= Decimal('5.00')
        self.op1.save()
        self.order.fees.create(
            fee_type=OrderFee.FEE_TYPE_PAYMENT,
            value=Decimal('5.00'),
        )
        self.order.status = Order.STATUS_PAID
        self.order.save()

        cancel_event(
            self.event.pk, subevent=None,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="10.00", keep_fees=[OrderFee.FEE_TYPE_PAYMENT],
            send=False, send_subject="Event canceled", send_message="Event canceled :-(", user=None
        )
        r = self.order.refunds.get()
        assert r.state == OrderRefund.REFUND_STATE_DONE
        assert r.amount == Decimal('36.90')
        assert r.source == OrderRefund.REFUND_SOURCE_ADMIN
        assert r.payment == p1
        assert self.order.all_logentries().filter(action_type='pretix.event.order.refund.created').exists()
        assert not self.order.all_logentries().filter(action_type='pretix.event.order.refund.requested').exists()
        assert gc.value == Decimal('36.90')

    @classscope(attr='o')
    def test_cancel_keep_some_fees(self):
        gc = self.o.issued_gift_cards.create(currency="EUR")
        self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='giftcard',
            info='{"gift_card": %d}' % gc.pk
        )
        self.op1.price -= Decimal('5.00')
        self.op1.save()
        self.order.fees.create(
            fee_type=OrderFee.FEE_TYPE_PAYMENT,
            value=Decimal('2.50'),
        )
        self.order.fees.create(
            fee_type=OrderFee.FEE_TYPE_SHIPPING,
            value=Decimal('2.50'),
        )
        self.order.status = Order.STATUS_PAID
        self.order.save()

        cancel_event(
            self.event.pk, subevent=None,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="10.00", keep_fees=[OrderFee.FEE_TYPE_PAYMENT],
            send=False, send_subject="Event canceled", send_message="Event canceled :-(",
            user=None
        )
        r = self.order.refunds.get()
        assert r.amount == Decimal('39.40')
        assert self.order.all_fees.get(fee_type=OrderFee.FEE_TYPE_SHIPPING).canceled
        assert not self.order.all_fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT).canceled
        assert self.order.all_fees.get(fee_type=OrderFee.FEE_TYPE_CANCELLATION).value == Decimal('4.10')

    @classscope(attr='o')
    def test_cancel_refund_paid_partial_to_manual(self):
        gc = self.o.issued_gift_cards.create(currency="EUR")
        p1 = self.order.payments.create(
            amount=Decimal('20.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='giftcard',
            info='{"gift_card": %d}' % gc.pk
        )
        self.order.payments.create(
            amount=Decimal('26.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='manual',
        )
        self.order.status = Order.STATUS_PAID
        self.order.save()

        cancel_event(
            self.event.pk, subevent=None, manual_refund=True,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="0.00",
            send=False, send_subject="Event canceled", send_message="Event canceled :-(",
            user=None
        )

        assert self.order.refunds.count() == 2
        r = self.order.refunds.get(provider='giftcard')
        assert r.state == OrderRefund.REFUND_STATE_DONE
        assert r.amount == Decimal('20.00')
        assert r.source == OrderRefund.REFUND_SOURCE_ADMIN
        assert r.payment == p1
        r = self.order.refunds.get(provider='manual')
        assert r.state == OrderRefund.REFUND_STATE_CREATED
        assert r.amount == Decimal('26.00')
        assert r.source == OrderRefund.REFUND_SOURCE_ADMIN
        assert r.payment is None

    @classscope(attr='o')
    def test_cancel_refund_paid_partial_no_manual(self):
        gc = self.o.issued_gift_cards.create(currency="EUR")
        p1 = self.order.payments.create(
            amount=Decimal('20.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='giftcard',
            info='{"gift_card": %d}' % gc.pk
        )
        self.order.payments.create(
            amount=Decimal('26.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='manual',
        )
        self.order.status = Order.STATUS_PAID
        self.order.save()

        cancel_event(
            self.event.pk, subevent=None, manual_refund=False,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="0.00",
            send=False, send_subject="Event canceled", send_message="Event canceled :-(",
            user=None
        )

        assert self.order.refunds.count() == 1
        r = self.order.refunds.get(provider='giftcard')
        assert r.state == OrderRefund.REFUND_STATE_DONE
        assert r.amount == Decimal('20.00')
        assert r.source == OrderRefund.REFUND_SOURCE_ADMIN
        assert r.payment == p1


class SubEventCancelTests(TestCase):
    def setUp(self):
        super().setUp()
        self.o = Organizer.objects.create(name='Dummy', slug='dummy')
        with scope(organizer=self.o):
            self.event = Event.objects.create(organizer=self.o, name='Dummy', slug='dummy', date_from=now(),
                                              plugins='tests.testdummy', has_subevents=True)
            self.se1 = self.event.subevents.create(name='One', date_from=now())
            self.se2 = self.event.subevents.create(name='Two', date_from=now())
            self.order = Order.objects.create(
                code='FOO', event=self.event, email='dummy@dummy.test',
                status=Order.STATUS_PENDING, locale='en',
                datetime=now(), expires=now() + timedelta(days=10),
                total=Decimal('46.00'),
            )
            self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                              default_price=Decimal('23.00'), admission=True)
            self.op1 = OrderPosition.objects.create(
                order=self.order, item=self.ticket, variation=None, subevent=self.se1,
                price=Decimal("23.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
            )
            self.op2 = OrderPosition.objects.create(
                order=self.order, item=self.ticket, variation=None, subevent=self.se2,
                price=Decimal("23.00"), attendee_name_parts={'full_name': "Dieter"}, positionid=2
            )
            generate_invoice(self.order)
            djmail.outbox = []

    @classscope(attr='o')
    def test_cancel_partially_send_mail_attendees(self):
        self.op1.attendee_email = 'foo@example.com'
        self.op1.save()
        self.op2.attendee_email = 'foo@example.org'
        self.op2.save()
        cancel_event(
            self.event.pk, subevent=self.se1.pk,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="0.00",
            send=True, send_subject="Event canceled", send_message="Event canceled :-(",
            user=None
        )
        assert len(djmail.outbox) == 2
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PENDING
        assert self.order.positions.count() == 1

    @classscope(attr='o')
    def test_cancel_simple_order(self):
        self.op2.subevent = self.se1
        self.op2.save()
        cancel_event(
            self.event.pk, subevent=self.se1.pk,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="0.00",
            send=True, send_subject="Event canceled", send_message="Event canceled :-(",
            user=None
        )
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_CANCELED

    @classscope(attr='o')
    def test_cancel_all_subevents(self):
        cancel_event(
            self.event.pk, subevent=None,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="0.00",
            send=True, send_subject="Event canceled", send_message="Event canceled :-(",
            user=None
        )
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_CANCELED

    @classscope(attr='o')
    def test_cancel_mixed_order(self):
        gc = self.o.issued_gift_cards.create(currency="EUR")
        self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='giftcard',
            info='{"gift_card": %d}' % gc.pk
        )
        self.order.status = Order.STATUS_PAID
        self.order.save()
        cancel_event(
            self.event.pk, subevent=self.se1.pk,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="0.00",
            send=True, send_subject="Event canceled", send_message="Event canceled :-( {refund_amount}",
            user=None
        )
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID
        assert '23.00' in djmail.outbox[0].body

    @classscope(attr='o')
    def test_cancel_partially_keep_fees(self):
        gc = self.o.issued_gift_cards.create(currency="EUR")
        p1 = self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='giftcard',
            info='{"gift_card": %d}' % gc.pk
        )
        self.op1.price -= Decimal('5.00')
        self.op1.save()
        self.order.fees.create(
            fee_type=OrderFee.FEE_TYPE_PAYMENT,
            value=Decimal('5.00'),
        )
        self.order.status = Order.STATUS_PAID
        self.order.save()

        cancel_event(
            self.event.pk, subevent=self.se1.pk,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="10.00",
            send=False, send_subject="Event canceled", send_message="Event canceled :-(",
            user=None
        )
        r = self.order.refunds.get()
        assert r.state == OrderRefund.REFUND_STATE_DONE
        assert r.amount == Decimal('16.20')
        assert r.source == OrderRefund.REFUND_SOURCE_ADMIN
        assert r.payment == p1
        assert self.order.all_logentries().filter(action_type='pretix.event.order.refund.created').exists()
        assert not self.order.all_logentries().filter(action_type='pretix.event.order.refund.requested').exists()
        assert gc.value == Decimal('16.20')
        assert self.order.positions.filter(subevent=self.se2).count() == 1
        assert self.order.positions.filter(subevent=self.se1).count() == 0
        f = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_CANCELLATION)
        assert f.value == Decimal('1.80')

    @classscope(attr='o')
    def test_cancel_send_mail_waitinglist(self):
        v = Voucher.objects.create(event=self.event, block_quota=True, redeemed=1)
        WaitingListEntry.objects.create(
            event=self.event, item=self.ticket, variation=None, email='foo@bar.com', voucher=v
        )
        WaitingListEntry.objects.create(
            event=self.event, item=self.ticket, variation=None, email='foo@example.org'
        )
        cancel_event(
            self.event.pk, subevent=None,
            auto_refund=True, keep_fee_fixed="0.00", keep_fee_percentage="0.00",
            send=False, send_subject="Event canceled", send_message="Event canceled :-(",
            send_waitinglist=True, send_waitinglist_message="Event canceled", send_waitinglist_subject=":(",
            user=None
        )
        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == ['foo@example.org']
