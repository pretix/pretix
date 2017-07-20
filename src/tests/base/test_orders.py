from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytz
from django.core import mail as djmail
from django.test import TestCase
from django.utils.timezone import make_aware, now

from pretix.base.decimal import round_decimal
from pretix.base.models import (
    CartPosition, Event, Item, Order, OrderPosition, Organizer,
)
from pretix.base.models.items import SubEventItem
from pretix.base.payment import FreeOrderProvider
from pretix.base.reldate import RelativeDate, RelativeDateWrapper
from pretix.base.services.invoices import generate_invoice
from pretix.base.services.orders import (
    OrderChangeManager, OrderError, _create_order, expire_orders,
    send_download_reminders,
)


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
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
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0, payment_provider='banktransfer'
    )
    o2 = Order.objects.create(
        code='FO2', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() - timedelta(days=10),
        total=0, payment_provider='banktransfer'
    )
    expire_orders(None)
    o1 = Order.objects.get(id=o1.id)
    assert o1.status == Order.STATUS_PENDING
    o2 = Order.objects.get(id=o2.id)
    assert o2.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_expiring_auto_disabled(event):
    event.settings.set('payment_term_expire_automatically', False)
    o1 = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0, payment_provider='banktransfer'
    )
    o2 = Order.objects.create(
        code='FO2', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() - timedelta(days=10),
        total=0, payment_provider='banktransfer'
    )
    expire_orders(None)
    o1 = Order.objects.get(id=o1.id)
    assert o1.status == Order.STATUS_PENDING
    o2 = Order.objects.get(id=o2.id)
    assert o2.status == Order.STATUS_PENDING


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
            total=Decimal('46.00'), payment_provider='banktransfer'
        )
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket', tax_rate=Decimal('7.00'),
                                          default_price=Decimal('23.00'), admission=True)
        self.op1 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name="Peter", positionid=1
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
        self.event = Event.objects.create(organizer=o, name='Dummy', slug='dummy', date_from=now(), plugins='pretix.plugins.banktransfer')
        self.order = Order.objects.create(
            code='FOO', event=self.event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, locale='en',
            datetime=now(), expires=now() + timedelta(days=10),
            total=Decimal('46.00'), payment_provider='banktransfer'
        )
        tr7 = self.event.tax_rules.create(rate=Decimal('7.00'))
        tr19 = self.event.tax_rules.create(rate=Decimal('19.00'))
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket', tax_rule=tr7,
                                          default_price=Decimal('23.00'), admission=True)
        self.ticket2 = Item.objects.create(event=self.event, name='Other ticket', tax_rule=tr7,
                                           default_price=Decimal('23.00'), admission=True)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', tax_rule=tr19,
                                         default_price=Decimal('12.00'))
        self.op1 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name="Peter", positionid=1
        )
        self.op2 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name="Dieter", positionid=2
        )
        self.ocm = OrderChangeManager(self.order, None)
        self.quota = self.event.quotas.create(name='Test', size=None)
        self.quota.items.add(self.ticket)
        self.quota.items.add(self.ticket2)
        self.quota.items.add(self.shirt)

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
        assert self.op1.tax_rate == self.shirt.tax_rate
        assert round_decimal(self.op1.price * (1 - 100 / (100 + self.op1.tax_rate))) == self.op1.tax_value
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

    def test_cancel_success(self):
        self.ocm.cancel(self.op1)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 1
        assert self.order.total == self.op2.price

    def test_free_to_paid(self):
        self.op1.price = Decimal('0.00')
        self.op1.save()
        self.op2.delete()
        self.order.total = Decimal('0.00')
        self.order.save()
        self.ocm.change_price(self.op1, Decimal('24.00'))
        with self.assertRaises(OrderError):
            self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.price == Decimal('0.00')

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
        self.event.settings.set('tax_rate_default', Decimal('19.00'))
        prov = self.ocm._get_payment_provider()
        prov.settings.set('_fee_abs', Decimal('0.30'))
        self.ocm.change_price(self.op1, Decimal('24.00'))
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('47.30')
        assert self.order.payment_fee == prov.calculate_fee(self.order.total)
        assert self.order.payment_fee_tax_rate == Decimal('19.00')
        assert round_decimal(self.order.payment_fee * (1 - 100 / (100 + self.order.payment_fee_tax_rate))) == self.order.payment_fee_tax_value

    def test_require_pending(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.ocm.change_item(self.op1, self.shirt, None)
        with self.assertRaises(OrderError):
            self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.item == self.ticket

    def test_change_price_to_free_marked_as_paid(self):
        self.ocm.change_price(self.op1, Decimal('0.00'))
        self.ocm.change_price(self.op2, Decimal('0.00'))
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == 0
        assert self.order.status == Order.STATUS_PAID
        assert self.order.payment_provider == 'free'

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
        with self.assertRaises(OrderError):
            self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == 46
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
        assert nop.tax_rate == self.shirt.tax_rate
        assert round_decimal(nop.price * (1 - 100 / (100 + self.shirt.tax_rate))) == nop.tax_value
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
        assert nop.tax_rate == self.shirt.tax_rate
        assert round_decimal(nop.price * (1 - 100 / (100 + self.shirt.tax_rate))) == nop.tax_value
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
