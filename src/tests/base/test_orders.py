from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytz
from django.core import mail as djmail
from django.test import TestCase
from django.utils.timezone import make_aware, now
from django_countries.fields import Country

from pretix.base.decimal import round_decimal
from pretix.base.models import (
    CartPosition, Event, InvoiceAddress, Item, Order, OrderPosition, Organizer,
)
from pretix.base.models.items import SubEventItem
from pretix.base.models.orders import OrderFee, OrderPayment, OrderRefund
from pretix.base.payment import FreeOrderProvider
from pretix.base.reldate import RelativeDate, RelativeDateWrapper
from pretix.base.services.invoices import generate_invoice
from pretix.base.services.orders import (
    OrderChangeManager, OrderError, _create_order, approve_order, deny_order,
    expire_orders, send_download_reminders, send_expiry_warnings,
)


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(),
        plugins='pretix.plugins.banktransfer'
    )
    return event


@pytest.mark.django_db
def test_expiry_days(event):
    today = now()
    event.settings.set('payment_term_days', 5)
    event.settings.set('payment_term_weekdays', False)
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today, payment_provider=FreeOrderProvider(event),
                          locale='de')
    assert (order.expires - today).days == 5


@pytest.mark.django_db
def test_expiry_weekdays(event):
    today = make_aware(datetime(2016, 9, 20, 15, 0, 0, 0))
    event.settings.set('payment_term_days', 5)
    event.settings.set('payment_term_weekdays', True)
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today, payment_provider=FreeOrderProvider(event),
                          locale='de')
    assert (order.expires - today).days == 6
    assert order.expires.weekday() == 0

    today = make_aware(datetime(2016, 9, 19, 15, 0, 0, 0))
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today, payment_provider=FreeOrderProvider(event),
                          locale='de')
    assert (order.expires - today).days == 7
    assert order.expires.weekday() == 0


@pytest.mark.django_db
def test_expiry_last(event):
    today = now()
    event.settings.set('payment_term_days', 5)
    event.settings.set('payment_term_weekdays', False)
    event.settings.set('payment_term_last', now() + timedelta(days=3))
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today, payment_provider=FreeOrderProvider(event),
                          locale='de')
    assert (order.expires - today).days == 3
    event.settings.set('payment_term_last', now() + timedelta(days=7))
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today, payment_provider=FreeOrderProvider(event),
                          locale='de')
    assert (order.expires - today).days == 5


@pytest.mark.django_db
def test_expiry_last_relative(event):
    today = now()
    event.settings.set('payment_term_days', 5)
    event.settings.set('payment_term_weekdays', False)
    event.date_from = now() + timedelta(days=5)
    event.save()
    event.settings.set('payment_term_last', RelativeDateWrapper(
        RelativeDate(days_before=2, time=None, base_date_name='date_from')
    ))
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today, payment_provider=FreeOrderProvider(event),
                          locale='de')
    assert (order.expires - today).days == 3


@pytest.mark.django_db
def test_expiry_last_relative_subevents(event):
    today = now()
    event.settings.set('payment_term_days', 100)
    event.settings.set('payment_term_weekdays', False)
    event.date_from = now() + timedelta(days=5)
    event.has_subevents = True
    event.save()
    tr7 = event.tax_rules.create(rate=Decimal('17.00'))
    ticket = Item.objects.create(event=event, name='Early-bird ticket', tax_rule=tr7,
                                 default_price=Decimal('23.00'), admission=True)

    se1 = event.subevents.create(name="SE1", date_from=now() + timedelta(days=10))
    se2 = event.subevents.create(name="SE2", date_from=now() + timedelta(days=8))

    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), subevent=se1, event=event, cart_id="123"
    )
    cp2 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), subevent=se2, event=event, cart_id="123"
    )

    event.settings.set('payment_term_last', RelativeDateWrapper(
        RelativeDate(days_before=2, time=None, base_date_name='date_from')
    ))
    order = _create_order(event, email='dummy@example.org', positions=[cp1, cp2],
                          now_dt=today, payment_provider=FreeOrderProvider(event),
                          locale='de')
    assert (order.expires - today).days == 6


@pytest.mark.django_db
def test_expiry_dst(event):
    event.settings.set('timezone', 'Europe/Berlin')
    tz = pytz.timezone('Europe/Berlin')
    utc = pytz.timezone('UTC')
    today = tz.localize(datetime(2016, 10, 29, 12, 0, 0)).astimezone(utc)
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today, payment_provider=FreeOrderProvider(event),
                          locale='de')
    localex = order.expires.astimezone(tz)
    assert (localex.hour, localex.minute) == (23, 59)


@pytest.mark.django_db
def test_expiring(event):
    o1 = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING, locale='en',
        datetime=now(), expires=now() + timedelta(days=10),
        total=0,
    )
    o2 = Order.objects.create(
        code='FO2', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING, locale='en',
        datetime=now(), expires=now() - timedelta(days=10),
        total=12,
    )
    generate_invoice(o2)
    expire_orders(None)
    o1 = Order.objects.get(id=o1.id)
    assert o1.status == Order.STATUS_PENDING
    o2 = Order.objects.get(id=o2.id)
    assert o2.status == Order.STATUS_EXPIRED
    assert o2.invoices.count() == 2
    assert o2.invoices.last().is_cancellation is True


@pytest.mark.django_db
def test_expiring_paid_invoice(event):
    o2 = Order.objects.create(
        code='FO2', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING, locale='en',
        datetime=now(), expires=now() - timedelta(days=10),
        total=12,
    )
    generate_invoice(o2)
    expire_orders(None)
    o2 = Order.objects.get(id=o2.id)
    assert o2.status == Order.STATUS_EXPIRED
    assert o2.invoices.count() == 2
    o2.payments.create(
        provider='manual', amount=o2.total
    ).confirm()
    assert o2.invoices.count() == 3
    assert o2.invoices.last().is_cancellation is False


@pytest.mark.django_db
def test_expiring_auto_disabled(event):
    event.settings.set('payment_term_expire_automatically', False)
    o1 = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0,
    )
    o2 = Order.objects.create(
        code='FO2', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() - timedelta(days=10),
        total=0,
    )
    expire_orders(None)
    o1 = Order.objects.get(id=o1.id)
    assert o1.status == Order.STATUS_PENDING
    o2 = Order.objects.get(id=o2.id)
    assert o2.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_do_not_expire_if_approval_pending(event):
    o1 = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() - timedelta(days=10),
        total=0, require_approval=True
    )
    o2 = Order.objects.create(
        code='FO2', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() - timedelta(days=10),
        total=0,
    )
    expire_orders(None)
    o1 = Order.objects.get(id=o1.id)
    assert o1.status == Order.STATUS_PENDING
    o2 = Order.objects.get(id=o2.id)
    assert o2.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_approve(event):
    djmail.outbox = []
    event.settings.invoice_generate = 'True'
    o1 = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() - timedelta(days=10),
        total=10, require_approval=True, locale='en'
    )
    approve_order(o1)
    o1.refresh_from_db()
    assert o1.expires > now()
    assert o1.status == Order.STATUS_PENDING
    assert not o1.require_approval
    assert o1.invoices.count() == 1
    assert len(djmail.outbox) == 1
    assert 'awaiting payment' in djmail.outbox[0].subject


@pytest.mark.django_db
def test_approve_free(event):
    djmail.outbox = []
    event.settings.invoice_generate = 'True'
    o1 = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() - timedelta(days=10),
        total=0, require_approval=True
    )
    approve_order(o1)
    o1.refresh_from_db()
    assert o1.expires > now()
    assert o1.status == Order.STATUS_PAID
    assert not o1.require_approval
    assert o1.invoices.count() == 0
    assert len(djmail.outbox) == 1
    assert 'confirmed' in djmail.outbox[0].subject


@pytest.mark.django_db
def test_deny(event):
    djmail.outbox = []
    event.settings.invoice_generate = 'True'
    o1 = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() - timedelta(days=10),
        total=10, require_approval=True, locale='en'
    )
    generate_invoice(o1)
    deny_order(o1)
    o1.refresh_from_db()
    assert o1.expires < now()
    assert o1.status == Order.STATUS_CANCELED
    assert o1.require_approval
    assert o1.invoices.count() == 2
    assert len(djmail.outbox) == 1
    assert 'denied' in djmail.outbox[0].subject


class PaymentReminderTests(TestCase):
    def setUp(self):
        super().setUp()
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now() + timedelta(days=2),
            plugins='pretix.plugins.banktransfer'
        )
        self.order = Order.objects.create(
            code='FOO', event=self.event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, locale='en',
            datetime=now(),
            expires=now() + timedelta(days=10),
            total=Decimal('46.00'),
        )
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          default_price=Decimal('23.00'), admission=True)
        self.op1 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
        )
        djmail.outbox = []

    def test_disabled(self):
        send_expiry_warnings(sender=self.event)
        assert len(djmail.outbox) == 0

    def test_sent_once(self):
        self.event.settings.mail_days_order_expire_warning = 12
        send_expiry_warnings(sender=self.event)
        assert len(djmail.outbox) == 1

    def test_paid(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        send_expiry_warnings(sender=self.event)
        assert len(djmail.outbox) == 0

    def test_sent_days(self):
        self.event.settings.mail_days_order_expire_warning = 9
        send_expiry_warnings(sender=self.event)
        assert len(djmail.outbox) == 0
        self.event.settings.mail_days_order_expire_warning = 10
        send_expiry_warnings(sender=self.event)
        assert len(djmail.outbox) == 1


class DownloadReminderTests(TestCase):
    def setUp(self):
        super().setUp()
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now() + timedelta(days=2),
            plugins='pretix.plugins.banktransfer'
        )
        self.order = Order.objects.create(
            code='FOO', event=self.event, email='dummy@dummy.test',
            status=Order.STATUS_PAID, locale='en',
            datetime=now(),
            expires=now() + timedelta(days=10),
            total=Decimal('46.00'),
        )
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          default_price=Decimal('23.00'), admission=True)
        self.op1 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name_parts={"full_name": "Peter"}, positionid=1
        )
        djmail.outbox = []

    def test_disabled(self):
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 0

    def test_sent_once(self):
        self.event.settings.mail_days_download_reminder = 2
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == ['dummy@dummy.test']
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 1

    def test_sent_paid_only(self):
        self.event.settings.mail_days_download_reminder = 2
        self.order.status = Order.STATUS_PENDING
        self.order.save()
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 0

    def test_not_sent_too_early(self):
        self.event.settings.mail_days_download_reminder = 1
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 0


class OrderChangeManagerTests(TestCase):
    def setUp(self):
        super().setUp()
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(organizer=o, name='Dummy', slug='dummy', date_from=now(),
                                          plugins='pretix.plugins.banktransfer')
        self.order = Order.objects.create(
            code='FOO', event=self.event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, locale='en',
            datetime=now(), expires=now() + timedelta(days=10),
            total=Decimal('46.00'),
        )
        self.order.payments.create(
            provider='banktransfer', state=OrderPayment.PAYMENT_STATE_CREATED, amount=self.order.total
        )
        self.tr7 = self.event.tax_rules.create(rate=Decimal('7.00'))
        self.tr19 = self.event.tax_rules.create(rate=Decimal('19.00'))
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket', tax_rule=self.tr7,
                                          default_price=Decimal('23.00'), admission=True)
        self.ticket2 = Item.objects.create(event=self.event, name='Other ticket', tax_rule=self.tr7,
                                           default_price=Decimal('23.00'), admission=True)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', tax_rule=self.tr19,
                                         default_price=Decimal('12.00'))
        self.op1 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
        )
        self.op2 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name_parts={'full_name': "Dieter"}, positionid=2
        )
        self.ocm = OrderChangeManager(self.order, None)
        self.quota = self.event.quotas.create(name='Test', size=None)
        self.quota.items.add(self.ticket)
        self.quota.items.add(self.ticket2)
        self.quota.items.add(self.shirt)

    def _enable_reverse_charge(self):
        self.tr7.eu_reverse_charge = True
        self.tr7.home_country = Country('DE')
        self.tr7.save()
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        return InvoiceAddress.objects.create(
            order=self.order, is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )

    def test_multiple_commits_forbidden(self):
        self.ocm.change_price(self.op1, Decimal('10.00'))
        self.ocm.commit()
        self.ocm.change_price(self.op1, Decimal('42.00'))
        with self.assertRaises(OrderError):
            self.ocm.commit()

    def test_change_subevent_quota_required(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        se2 = self.event.subevents.create(name="Bar", date_from=now())
        self.op1.subevent = se1
        self.op1.save()
        self.quota.subevent = se1
        self.quota.save()
        with self.assertRaises(OrderError):
            self.ocm.change_subevent(self.op1, se2)

    def test_change_subevent_success(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        se2 = self.event.subevents.create(name="Bar", date_from=now())
        SubEventItem.objects.create(subevent=se2, item=self.ticket, price=12)
        self.op1.subevent = se1
        self.op1.save()
        self.quota.subevent = se2
        self.quota.save()

        self.ocm.change_subevent(self.op1, se2)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.subevent == se2
        assert self.op1.price == 12
        assert self.order.total == self.op1.price + self.op2.price

    def test_change_subevent_reverse_charge(self):
        self._enable_reverse_charge()
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        se2 = self.event.subevents.create(name="Bar", date_from=now())
        SubEventItem.objects.create(subevent=se2, item=self.ticket, price=10.7)
        self.op1.subevent = se1
        self.op1.save()
        self.quota.subevent = se2
        self.quota.save()

        self.ocm.change_subevent(self.op1, se2)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.subevent == se2
        assert self.op1.price == Decimal('10.00')
        assert self.op1.tax_value == Decimal('0.00')
        assert self.order.total == self.op1.price + self.op2.price

    def test_change_subevent_net_price(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        se2 = self.event.subevents.create(name="Bar", date_from=now())
        self.tr7.price_includes_tax = False
        self.tr7.save()
        SubEventItem.objects.create(subevent=se2, item=self.ticket, price=10)
        self.op1.subevent = se1
        self.op1.save()
        self.quota.subevent = se2
        self.quota.save()

        self.ocm.change_subevent(self.op1, se2)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.subevent == se2
        assert self.op1.price == Decimal('10.70')
        assert self.order.total == self.op1.price + self.op2.price

    def test_change_subevent_sold_out(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        se2 = self.event.subevents.create(name="Bar", date_from=now())
        self.op1.subevent = se1
        self.op1.save()
        self.quota.subevent = se2
        self.quota.size = 0
        self.quota.save()

        self.ocm.change_subevent(self.op1, se2)
        with self.assertRaises(OrderError):
            self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.subevent == se1

    def test_change_item_quota_required(self):
        self.quota.delete()
        with self.assertRaises(OrderError):
            self.ocm.change_item(self.op1, self.shirt, None)

    def test_change_item_success(self):
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.shirt
        assert self.op1.price == self.shirt.default_price
        assert self.op1.tax_rate == self.shirt.tax_rule.rate
        assert round_decimal(self.op1.price * (1 - 100 / (100 + self.op1.tax_rate))) == self.op1.tax_value
        assert self.order.total == self.op1.price + self.op2.price

    def test_change_item_net_price_success(self):
        self.tr19.price_includes_tax = False
        self.tr19.save()
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.shirt
        assert self.op1.price == Decimal('14.28')
        assert self.op1.tax_rate == self.shirt.tax_rule.rate
        assert round_decimal(self.op1.price * (1 - 100 / (100 + self.op1.tax_rate))) == self.op1.tax_value
        assert self.order.total == self.op1.price + self.op2.price

    def test_change_item_reverse_charge(self):
        self._enable_reverse_charge()
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.shirt
        assert self.op1.price == Decimal('10.08')
        assert self.op1.tax_rate == Decimal('0.00')
        assert self.op1.tax_value == Decimal('0.00')
        assert self.order.total == self.op1.price + self.op2.price

    def test_change_price_success(self):
        self.ocm.change_price(self.op1, Decimal('24.00'))
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.ticket
        assert self.op1.price == Decimal('24.00')
        assert round_decimal(self.op1.price * (1 - 100 / (100 + self.op1.tax_rate))) == self.op1.tax_value
        assert self.order.total == self.op1.price + self.op2.price

    def test_change_price_net_success(self):
        self.tr7.price_includes_tax = False
        self.tr7.save()
        self.ocm.change_price(self.op1, Decimal('10.00'))
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.ticket
        assert self.op1.price == Decimal('10.70')
        assert round_decimal(self.op1.price * (1 - 100 / (100 + self.op1.tax_rate))) == self.op1.tax_value
        assert self.order.total == self.op1.price + self.op2.price

    def test_cancel_success(self):
        self.ocm.cancel(self.op1)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 1
        assert self.order.total == self.op2.price

    def test_free_to_paid(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.op1.price = Decimal('0.00')
        self.op1.save()
        self.op2.delete()
        self.order.total = Decimal('0.00')
        self.order.save()
        self.ocm.change_price(self.op1, Decimal('24.00'))
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.price == Decimal('24.00')
        assert self.order.status == Order.STATUS_PENDING

    def test_cancel_all_in_order(self):
        self.ocm.cancel(self.op1)
        self.ocm.cancel(self.op2)
        with self.assertRaises(OrderError):
            self.ocm.commit()
        assert self.order.positions.count() == 2

    def test_empty(self):
        self.ocm.commit()

    def test_quota_unlimited(self):
        q = self.event.quotas.create(name='Test', size=None)
        q.items.add(self.shirt)
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.item == self.shirt

    def test_quota_full(self):
        q = self.event.quotas.create(name='Test', size=0)
        q.items.add(self.shirt)
        self.ocm.change_item(self.op1, self.shirt, None)
        with self.assertRaises(OrderError):
            self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.item == self.ticket

    def test_quota_full_but_in_same(self):
        q = self.event.quotas.create(name='Test', size=0)
        q.items.add(self.shirt)
        q.items.add(self.ticket)
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.item == self.shirt

    def test_multiple_quotas_shared_full(self):
        q1 = self.event.quotas.create(name='Test', size=0)
        q2 = self.event.quotas.create(name='Test', size=2)
        q1.items.add(self.shirt)
        q1.items.add(self.ticket)
        q2.items.add(self.shirt)
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.item == self.shirt

    def test_multiple_quotas_unshared_full(self):
        q1 = self.event.quotas.create(name='Test', size=2)
        q2 = self.event.quotas.create(name='Test', size=0)
        q1.items.add(self.shirt)
        q1.items.add(self.ticket)
        q2.items.add(self.shirt)
        self.ocm.change_item(self.op1, self.shirt, None)
        with self.assertRaises(OrderError):
            self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.item == self.ticket

    def test_multiple_items_success(self):
        q1 = self.event.quotas.create(name='Test', size=2)
        q1.items.add(self.shirt)
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.change_item(self.op2, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.op2.refresh_from_db()
        assert self.op1.item == self.shirt
        assert self.op2.item == self.shirt

    def test_multiple_items_quotas_partially_full(self):
        q1 = self.event.quotas.create(name='Test', size=1)
        q1.items.add(self.shirt)
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.change_item(self.op2, self.shirt, None)
        with self.assertRaises(OrderError):
            self.ocm.commit()
        self.op1.refresh_from_db()
        self.op2.refresh_from_db()
        assert self.op1.item == self.ticket
        assert self.op2.item == self.ticket

    def test_payment_fee_calculation(self):
        self.event.settings.set('tax_rate_default', self.tr19.pk)
        prov = self.ocm._get_payment_provider()
        prov.settings.set('_fee_abs', Decimal('0.30'))
        self.ocm.change_price(self.op1, Decimal('24.00'))
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('47.30')
        fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == prov.calculate_fee(self.order.total)
        assert fee.tax_rate == Decimal('19.00')
        assert round_decimal(fee.value * (1 - 100 / (100 + fee.tax_rate))) == fee.tax_value

    def test_pending_free_order_stays_pending(self):
        self.event.settings.set('tax_rate_default', self.tr19.pk)
        self.ocm.change_price(self.op1, Decimal('0.00'))
        self.ocm.change_price(self.op2, Decimal('0.00'))
        self.ocm.commit()
        self.ocm = OrderChangeManager(self.order, None)
        self.order.refresh_from_db()
        assert self.order.total == Decimal('0.00')
        assert self.order.status == Order.STATUS_PAID
        self.order.status = Order.STATUS_PENDING
        self.ocm.cancel(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PENDING

    def test_require_pending(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.item == self.shirt

    def test_change_price_to_free_marked_as_paid(self):
        self.ocm.change_price(self.op1, Decimal('0.00'))
        self.ocm.change_price(self.op2, Decimal('0.00'))
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == 0
        assert self.order.status == Order.STATUS_PAID
        assert self.order.payments.last().provider == 'free'

    def test_change_paid_same_price(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.ocm.change_item(self.op1, self.ticket2, None)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == 46
        assert self.order.status == Order.STATUS_PAID

    def test_change_paid_different_price(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.ocm.change_price(self.op1, Decimal('5.00'))
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('28.00')
        assert self.order.status == Order.STATUS_PAID

    def test_change_paid_to_pending(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.order.payments.create(
            provider='manual',
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            amount=self.order.total,
        )
        self.ocm.change_price(self.op1, Decimal('25.00'))
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('48.00')
        assert self.order.pending_sum == Decimal('2.00')
        assert self.order.status == Order.STATUS_PENDING

    def test_change_paid_stays_paid_when_overpaid(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.order.payments.create(
            provider='manual',
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            amount=self.order.total,
        )
        self.order.payments.create(
            provider='manual',
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            amount=Decimal('2.00'),
        )
        assert self.order.pending_sum == Decimal('-2.00')
        self.ocm.change_price(self.op1, Decimal('25.00'))
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('48.00')
        assert self.order.pending_sum == Decimal('0.00')
        assert self.order.status == Order.STATUS_PAID

    def test_add_item_quota_required(self):
        self.quota.delete()
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.shirt, None, None, None)

    def test_add_item_success(self):
        self.ocm.add_position(self.shirt, None, None, None)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 3
        nop = self.order.positions.last()
        assert nop.item == self.shirt
        assert nop.price == self.shirt.default_price
        assert nop.tax_rate == self.shirt.tax_rule.rate
        assert round_decimal(nop.price * (1 - 100 / (100 + self.shirt.tax_rule.rate))) == nop.tax_value
        assert self.order.total == self.op1.price + self.op2.price + nop.price
        assert nop.positionid == 3

    def test_add_item_net_price_success(self):
        self.tr19.price_includes_tax = False
        self.tr19.save()
        self.ocm.add_position(self.shirt, None, None, None)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 3
        nop = self.order.positions.last()
        assert nop.item == self.shirt
        assert nop.price == Decimal('14.28')
        assert nop.tax_rate == self.shirt.tax_rule.rate
        assert round_decimal(nop.price * (1 - 100 / (100 + self.shirt.tax_rule.rate))) == nop.tax_value
        assert self.order.total == self.op1.price + self.op2.price + nop.price
        assert nop.positionid == 3

    def test_add_item_reverse_charge(self):
        self._enable_reverse_charge()
        self.ocm.add_position(self.shirt, None, None, None)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 3
        nop = self.order.positions.last()
        assert nop.item == self.shirt
        assert nop.price == Decimal('10.08')
        assert nop.tax_rate == Decimal('0.00')
        assert nop.tax_value == Decimal('0.00')
        assert self.order.total == self.op1.price + self.op2.price + nop.price
        assert nop.positionid == 3

    def test_add_item_custom_price(self):
        self.ocm.add_position(self.shirt, None, Decimal('13.00'), None)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 3
        nop = self.order.positions.last()
        assert nop.item == self.shirt
        assert nop.price == Decimal('13.00')
        assert nop.tax_rate == self.shirt.tax_rule.rate
        assert round_decimal(nop.price * (1 - 100 / (100 + self.shirt.tax_rule.rate))) == nop.tax_value
        assert self.order.total == self.op1.price + self.op2.price + nop.price

    def test_add_item_custom_price_tax_always_included(self):
        self.tr19.price_includes_tax = False
        self.tr19.save()
        self.ocm.add_position(self.shirt, None, Decimal('11.90'), None)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 3
        nop = self.order.positions.last()
        assert nop.item == self.shirt
        assert nop.price == Decimal('11.90')
        assert nop.tax_rate == self.shirt.tax_rule.rate
        assert round_decimal(nop.price * (1 - 100 / (100 + self.shirt.tax_rule.rate))) == nop.tax_value
        assert self.order.total == self.op1.price + self.op2.price + nop.price

    def test_add_item_quota_full(self):
        q1 = self.event.quotas.create(name='Test', size=0)
        q1.items.add(self.shirt)
        self.ocm.add_position(self.shirt, None, None, None)
        with self.assertRaises(OrderError):
            self.ocm.commit()
        assert self.order.positions.count() == 2

    def test_add_item_addon(self):
        self.shirt.category = self.event.categories.create(name='Add-ons', is_addon=True)
        self.ticket.addons.create(addon_category=self.shirt.category)
        self.ocm.add_position(self.shirt, None, Decimal('13.00'), self.op1)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 3
        nop = self.order.positions.last()
        assert nop.item == self.shirt
        assert nop.addon_to == self.op1

    def test_add_item_addon_invalid(self):
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.shirt, None, Decimal('13.00'), self.op1)
        self.shirt.category = self.event.categories.create(name='Add-ons', is_addon=True)
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.shirt, None, Decimal('13.00'), None)

    def test_add_item_subevent_required(self):
        self.event.has_subevents = True
        self.event.save()
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.ticket, None, None, None)

    def test_add_item_subevent_price(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        SubEventItem.objects.create(subevent=se1, item=self.ticket, price=12)
        self.quota.subevent = se1
        self.quota.save()

        self.ocm.add_position(self.ticket, None, None, subevent=se1)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 3
        nop = self.order.positions.last()
        assert nop.item == self.ticket
        assert nop.price == Decimal('12.00')
        assert nop.subevent == se1

    def test_reissue_invoice(self):
        generate_invoice(self.order)
        assert self.order.invoices.count() == 1
        self.ocm.add_position(self.ticket, None, Decimal('0.00'))
        self.ocm.commit()
        assert self.order.invoices.count() == 3

    def test_dont_reissue_invoice_on_free_product_changes(self):
        self.event.settings.invoice_include_free = False
        generate_invoice(self.order)
        assert self.order.invoices.count() == 1
        self.ocm.add_position(self.ticket, None, Decimal('0.00'))
        self.ocm.commit()
        assert self.order.invoices.count() == 1

    def test_recalculate_reverse_charge(self):
        self.event.settings.set('tax_rate_default', self.tr19.pk)
        prov = self.ocm._get_payment_provider()
        prov.settings.set('_fee_abs', Decimal('0.30'))
        self.ocm._recalculate_total_and_payment_fee()

        assert self.order.total == Decimal('46.30')
        fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == prov.calculate_fee(self.order.total)
        assert fee.tax_rate == Decimal('19.00')
        assert fee.tax_value == Decimal('0.05')

        self.ocm = OrderChangeManager(self.order, None)
        ia = self._enable_reverse_charge()
        self.ocm.recalculate_taxes()
        self.ocm.commit()
        ops = list(self.order.positions.all())
        for op in ops:
            assert op.price == Decimal('21.50')
            assert op.tax_value == Decimal('0.00')
            assert op.tax_rate == Decimal('0.00')

        assert self.order.total == Decimal('43.30')
        fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == prov.calculate_fee(self.order.total)
        assert fee.tax_rate == Decimal('0.00')
        assert fee.tax_value == Decimal('0.00')

        ia.vat_id_validated = False
        ia.save()

        self.ocm = OrderChangeManager(self.order, None)
        self.ocm.recalculate_taxes()
        self.ocm.commit()
        ops = list(self.order.positions.all())
        for op in ops:
            assert op.price == Decimal('23.01')   # sic. we can't really avoid it.
            assert op.tax_value == Decimal('1.51')
            assert op.tax_rate == Decimal('7.00')

        assert self.order.total == Decimal('46.32')
        fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == prov.calculate_fee(self.order.total)
        assert fee.tax_rate == Decimal('19.00')
        assert fee.tax_value == Decimal('0.05')

    def test_split_simple(self):
        old_secret = self.op2.secret
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()
        assert self.order.total == Decimal('23.00')
        assert self.order.positions.count() == 1
        assert self.op2.order != self.order
        o2 = self.op2.order
        assert o2.total == Decimal('23.00')
        assert o2.positions.count() == 1
        assert o2.code != self.order.code
        assert o2.secret != self.order.secret
        assert o2.datetime > self.order.datetime
        assert self.op2.secret != old_secret
        assert not self.order.invoices.exists()
        assert not o2.invoices.exists()

    def test_split_pending_payment_fees(self):
        # Set payment fees
        self.event.settings.set('tax_rate_default', self.tr19.pk)
        prov = self.ocm._get_payment_provider()
        prov.settings.set('_fee_percent', Decimal('2.00'))
        prov.settings.set('_fee_abs', Decimal('1.00'))
        prov.settings.set('_fee_reverse_calc', False)
        self.ocm.change_price(self.op1, Decimal('23.00'))
        self.ocm.commit()
        self.ocm = OrderChangeManager(self.order, None)
        self.order.refresh_from_db()
        assert self.order.total == Decimal('47.92')
        fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == Decimal('1.92')
        assert fee.tax_rate == Decimal('19.00')

        # Split
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()

        # First order
        assert self.order.total == Decimal('24.46')
        fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == Decimal('1.46')
        assert fee.tax_rate == Decimal('19.00')
        assert self.order.positions.count() == 1
        assert self.order.fees.count() == 1

        # New order
        assert self.op2.order != self.order
        o2 = self.op2.order
        assert o2.total == Decimal('24.46')
        fee = o2.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == Decimal('1.46')
        assert fee.tax_rate == Decimal('19.00')
        assert o2.positions.count() == 1
        assert o2.fees.count() == 1

    def test_split_paid_no_payment_fees(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.order.payments.create(
            provider='manual',
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            amount=self.order.total,
        )

        # Split
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()

        # First order
        assert self.order.total == Decimal('23.00')
        assert not self.order.fees.exists()
        assert self.order.pending_sum == Decimal('0.00')
        r = self.order.refunds.last()
        assert r.provider == 'offsetting'
        assert r.amount == Decimal('23.00')
        assert r.state == OrderRefund.REFUND_STATE_DONE

        # New order
        assert self.op2.order != self.order
        o2 = self.op2.order
        assert o2.total == Decimal('23.00')
        assert o2.status == Order.STATUS_PAID
        assert o2.positions.count() == 1
        assert o2.fees.count() == 0
        assert o2.pending_sum == Decimal('0.00')
        p = o2.payments.last()
        assert p.provider == 'offsetting'
        assert p.amount == Decimal('23.00')
        assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED

    def test_split_invoice_address(self):
        ia = InvoiceAddress.objects.create(
            order=self.order, is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT'), company='Sample'
        )

        # Split
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()

        # First order
        assert self.order.total == Decimal('23.00')
        assert self.order.invoice_address == ia

        # New order
        assert self.op2.order != self.order
        o2 = self.op2.order
        o2.refresh_from_db()
        ia = InvoiceAddress.objects.get(pk=ia.pk)
        assert o2.total == Decimal('23.00')
        assert o2.positions.count() == 1
        assert o2.invoice_address != ia
        assert o2.invoice_address.company == 'Sample'

    def test_change_price_of_pending_order_with_payment(self):
        self.order.status = Order.STATUS_PENDING
        self.order.save()
        assert self.order.payments.last().state == OrderPayment.PAYMENT_STATE_CREATED
        assert self.order.payments.last().amount == Decimal('46.00')

        self.ocm.change_price(self.op1, Decimal('27.00'))
        self.ocm.commit()

        assert self.order.payments.last().state == OrderPayment.PAYMENT_STATE_CANCELED
        assert self.order.payments.last().amount == Decimal('46.00')

    def test_split_reverse_charge(self):
        ia = self._enable_reverse_charge()

        # Set payment fees
        self.event.settings.set('tax_rate_default', self.tr19.pk)
        prov = self.ocm._get_payment_provider()
        prov.settings.set('_fee_percent', Decimal('2.00'))
        prov.settings.set('_fee_reverse_calc', False)
        self.ocm.recalculate_taxes()
        self.ocm.commit()
        self.ocm = OrderChangeManager(self.order, None)
        self.order.refresh_from_db()

        # Check if reverse charge is active
        assert self.order.total == Decimal('43.86')
        fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == Decimal('0.86')
        assert fee.tax_rate == Decimal('0.00')
        self.op1.refresh_from_db()
        self.op2.refresh_from_db()
        assert self.op1.price == Decimal('21.50')
        assert self.op2.price == Decimal('21.50')

        # Split
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()

        # First order
        assert self.order.total == Decimal('21.93')
        fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == Decimal('0.43')
        assert fee.tax_rate == Decimal('0.00')
        assert fee.tax_value == Decimal('0.00')
        assert self.order.positions.count() == 1
        assert self.order.fees.count() == 1
        assert self.order.positions.first().price == Decimal('21.50')
        assert self.order.positions.first().tax_value == Decimal('0.00')

        # New order
        assert self.op2.order != self.order
        o2 = self.op2.order
        assert o2.total == Decimal('21.93')
        fee = o2.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == Decimal('0.43')
        assert fee.tax_rate == Decimal('0.00')
        assert fee.tax_value == Decimal('0.00')
        assert o2.positions.count() == 1
        assert o2.positions.first().price == Decimal('21.50')
        assert o2.positions.first().tax_value == Decimal('0.00')
        assert o2.fees.count() == 1
        ia = InvoiceAddress.objects.get(pk=ia.pk)
        assert o2.invoice_address != ia
        assert o2.invoice_address.vat_id_validated is True

    def test_split_other_fees(self):
        # Check if reverse charge is active
        self.order.fees.create(fee_type=OrderFee.FEE_TYPE_SHIPPING, tax_rule=self.tr19, value=Decimal('2.50'))
        self.order.total += Decimal('2.50')
        self.order.save()

        # Split
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()

        # First order
        assert self.order.total == Decimal('25.50')
        fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_SHIPPING)
        assert fee.value == Decimal('2.50')
        assert fee.tax_value == Decimal('0.40')
        assert self.order.positions.count() == 1
        assert self.order.fees.count() == 1

        # New order
        assert self.op2.order != self.order
        o2 = self.op2.order
        assert o2.total == Decimal('25.50')
        fee = o2.fees.get(fee_type=OrderFee.FEE_TYPE_SHIPPING)
        assert fee.value == Decimal('2.50')
        assert fee.tax_value == Decimal('0.40')
        assert o2.positions.count() == 1
        assert o2.positions.first().price == Decimal('23.00')
        assert o2.fees.count() == 1

    def test_split_to_empty(self):
        self.ocm.split(self.op1)
        self.ocm.split(self.op2)
        with self.assertRaises(OrderError):
            self.ocm.commit()

    def test_split_paid_payment_fees(self):
        # Set payment fees
        self.event.settings.set('tax_rate_default', self.tr19.pk)
        prov = self.ocm._get_payment_provider()
        prov.settings.set('_fee_percent', Decimal('2.00'))
        prov.settings.set('_fee_abs', Decimal('1.00'))
        prov.settings.set('_fee_reverse_calc', False)
        self.ocm.change_price(self.op1, Decimal('23.00'))
        self.ocm.commit()
        self.ocm = OrderChangeManager(self.order, None)
        self.order.refresh_from_db()
        assert self.order.total == Decimal('47.92')
        fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == Decimal('1.92')
        assert fee.tax_rate == Decimal('19.00')

        self.order.status = Order.STATUS_PAID
        self.order.save()
        payment = self.order.payments.first()
        payment.state = OrderPayment.PAYMENT_STATE_CONFIRMED
        payment.save()

        # Split
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()

        # First order
        assert self.order.total == Decimal('24.92')
        fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == Decimal('1.92')
        assert fee.tax_rate == Decimal('19.00')
        assert self.order.positions.count() == 1
        assert self.order.fees.count() == 1

        # New order
        assert self.op2.order != self.order
        o2 = self.op2.order
        assert o2.total == Decimal('23.00')
        assert o2.fees.count() == 0

    def test_split_invoice(self):
        generate_invoice(self.order)
        assert self.order.invoices.count() == 1
        assert self.order.invoices.last().lines.count() == 2
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()
        o2 = self.op2.order

        assert self.order.invoices.count() == 3
        assert self.order.invoices.last().lines.count() == 1
        assert o2.invoices.count() == 1
        assert o2.invoices.last().lines.count() == 1

    def test_split_to_free_invoice(self):
        self.event.settings.invoice_include_free = False
        self.ocm.change_price(self.op2, Decimal('0.00'))
        self.ocm.commit()
        self.ocm = OrderChangeManager(self.order, None)
        self.op2.refresh_from_db()
        self.ocm._invoice_dirty = False

        generate_invoice(self.order)
        assert self.order.invoices.count() == 1
        assert self.order.invoices.last().lines.count() == 1
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()
        o2 = self.op2.order

        assert self.order.invoices.count() == 1
        assert self.order.invoices.last().lines.count() == 1
        assert o2.invoices.count() == 0

    def test_split_to_original_free(self):
        self.ocm.change_price(self.op2, Decimal('0.00'))
        self.ocm.commit()
        self.ocm = OrderChangeManager(self.order, None)
        self.op2.refresh_from_db()

        self.ocm.split(self.op1)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()
        o2 = self.op1.order

        assert self.order.total == Decimal('0.00')
        assert self.order.status == Order.STATUS_PAID
        assert o2.total == Decimal('23.00')
        assert o2.status == Order.STATUS_PENDING

    def test_split_to_new_free(self):
        self.ocm.change_price(self.op2, Decimal('0.00'))
        self.ocm.commit()
        self.ocm = OrderChangeManager(self.order, None)
        self.op2.refresh_from_db()

        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()
        o2 = self.op2.order

        assert self.order.total == Decimal('23.00')
        assert self.order.status == Order.STATUS_PENDING
        assert o2.total == Decimal('0.00')
        assert o2.status == Order.STATUS_PAID
