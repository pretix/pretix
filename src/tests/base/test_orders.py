#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytz
from django.core import mail as djmail
from django.db.models import F, Sum
from django.test import TestCase
from django.utils.timezone import make_aware, now
from django_countries.fields import Country
from django_scopes import scope
from tests.testdummy.signals import FoobazSalesChannel

from pretix.base.decimal import round_decimal
from pretix.base.models import (
    CartPosition, Event, GiftCard, InvoiceAddress, Item, Order, OrderPosition,
    Organizer, SeatingPlan,
)
from pretix.base.models.items import SubEventItem
from pretix.base.models.orders import OrderFee, OrderPayment, OrderRefund
from pretix.base.payment import (
    FreeOrderProvider, GiftCardPayment, PaymentException,
)
from pretix.base.reldate import RelativeDate, RelativeDateWrapper
from pretix.base.secrets import assign_ticket_secret
from pretix.base.services.invoices import generate_invoice
from pretix.base.services.orders import (
    OrderChangeManager, OrderError, _create_order, approve_order, cancel_order,
    deny_order, expire_orders, reactivate_order, send_download_reminders,
    send_expiry_warnings,
)
from pretix.plugins.banktransfer.payment import BankTransfer
from pretix.testutils.scope import classscope


@pytest.fixture(scope='function')
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(),
        plugins='pretix.plugins.banktransfer'
    )
    with scope(organizer=o):
        yield event


@pytest.fixture
def clist_autocheckin(event):
    c = event.checkin_lists.create(name="Default", all_products=True, auto_checkin_sales_channels=['web'])
    return c


@pytest.mark.django_db
def test_expiry_days(event):
    today = now()
    event.settings.set('payment_term_days', 5)
    event.settings.set('payment_term_weekdays', False)
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de')[0]
    assert (order.expires - today).days == 5


@pytest.mark.django_db
def test_expiry_weekdays(event):
    today = make_aware(datetime(2016, 9, 20, 15, 0, 0, 0))
    event.settings.set('payment_term_days', 5)
    event.settings.set('payment_term_weekdays', True)
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de')[0]
    assert (order.expires - today).days == 6
    assert order.expires.weekday() == 0

    today = make_aware(datetime(2016, 9, 19, 15, 0, 0, 0))
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de')[0]
    assert (order.expires - today).days == 7
    assert order.expires.weekday() == 0


@pytest.mark.django_db
def test_expiry_minutes(event):
    today = now()
    event.settings.set('payment_term_days', 5)
    event.settings.set('payment_term_mode', 'minutes')
    event.settings.set('payment_term_minutes', 30)
    event.settings.set('payment_term_weekdays', False)
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de')[0]
    assert (order.expires - today).days == 0
    assert (order.expires - today).seconds == 30 * 60


@pytest.mark.django_db
def test_expiry_last(event):
    today = now()
    event.settings.set('payment_term_days', 5)
    event.settings.set('payment_term_weekdays', False)
    event.settings.set('payment_term_last', now() + timedelta(days=3))
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de')[0]
    assert (order.expires - today).days == 3
    event.settings.set('payment_term_last', now() + timedelta(days=7))
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de')[0]
    assert (order.expires - today).days == 5


@pytest.mark.django_db
def test_expiry_last_relative(event):
    today = now()
    event.settings.set('payment_term_days', 5)
    event.settings.set('payment_term_weekdays', False)
    event.date_from = now() + timedelta(days=5)
    event.save()
    event.settings.set('payment_term_last', RelativeDateWrapper(
        RelativeDate(days_before=2, time=None, base_date_name='date_from', minutes_before=None)
    ))
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de')[0]
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
        RelativeDate(days_before=2, time=None, base_date_name='date_from', minutes_before=None)
    ))
    order = _create_order(event, email='dummy@example.org', positions=[cp1, cp2],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de')[0]
    assert (order.expires - today).days == 6


@pytest.mark.django_db
def test_expiry_dst(event):
    event.settings.set('timezone', 'Europe/Berlin')
    tz = pytz.timezone('Europe/Berlin')
    utc = pytz.timezone('UTC')
    today = tz.localize(datetime(2016, 10, 29, 12, 0, 0)).astimezone(utc)
    order = _create_order(event, email='dummy@example.org', positions=[],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de')[0]
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
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 default_price=Decimal('23.00'), admission=True)
    OrderPosition.objects.create(
        order=o1, item=ticket, variation=None,
        price=Decimal("0.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
    )
    OrderPosition.objects.create(
        order=o2, item=ticket, variation=None,
        price=Decimal("12.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
    )
    generate_invoice(o2)
    o1.create_transactions()
    o2.create_transactions()
    expire_orders(None)
    o1 = Order.objects.get(id=o1.id)
    assert o1.status == Order.STATUS_PENDING
    o2 = Order.objects.get(id=o2.id)
    assert o2.status == Order.STATUS_EXPIRED
    assert o2.invoices.count() == 2
    assert o2.invoices.last().is_cancellation is True
    assert o1.transactions.count() == 1
    assert o2.transactions.count() == 2
    assert o2.transactions.aggregate(s=Sum(F('price') * F('count')))['s'] == Decimal('0.00')


@pytest.mark.django_db
def test_expiring_paid_invoice(event):
    o2 = Order.objects.create(
        code='FO2', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING, locale='en',
        datetime=now(), expires=now() - timedelta(days=10),
        total=12,
    )
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 default_price=Decimal('12.00'), admission=True)
    q = event.quotas.create(name='Q', size=None)
    q.items.add(ticket)
    OrderPosition.objects.create(
        order=o2, item=ticket, variation=None,
        price=Decimal("12.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
    )
    generate_invoice(o2)
    o2.create_transactions()
    assert o2.transactions.aggregate(s=Sum(F('price') * F('count')))['s'] == Decimal('12.00')
    expire_orders(None)
    assert o2.transactions.aggregate(s=Sum(F('price') * F('count')))['s'] == Decimal('0.00')
    o2 = Order.objects.get(id=o2.id)
    assert o2.status == Order.STATUS_EXPIRED
    assert o2.invoices.count() == 2
    o2.payments.create(
        provider='manual', amount=o2.total
    ).confirm()
    assert o2.invoices.count() == 3
    assert o2.invoices.last().is_cancellation is False
    assert o2.transactions.count() == 3
    assert o2.transactions.aggregate(s=Sum(F('price') * F('count')))['s'] == Decimal('12.00')


@pytest.mark.django_db
def test_expire_twice(event):
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
    # this would usually happen when the deadline is extended, but lets keep the case simple
    o2.status = Order.STATUS_PENDING
    o2.save()
    expire_orders(None)
    o2 = Order.objects.get(id=o2.id)
    assert o2.status == Order.STATUS_EXPIRED
    assert o2.invoices.count() == 2


@pytest.mark.django_db
def test_expire_skipped_if_canceled_with_fee(event):
    o2 = Order.objects.create(
        code='FO2', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING, locale='en',
        datetime=now(), expires=now() - timedelta(days=10),
        total=12,
    )
    o2.fees.create(fee_type=OrderFee.FEE_TYPE_CANCELLATION, value=12)
    generate_invoice(o2)
    expire_orders(None)
    o2 = Order.objects.get(id=o2.id)
    assert o2.status == Order.STATUS_PENDING


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
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 default_price=Decimal('23.00'), admission=True)
    OrderPosition.objects.create(
        order=o1, item=ticket, variation=None,
        price=Decimal("23.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
    )
    o1.create_transactions()
    assert o1.transactions.count() == 0
    approve_order(o1)
    o1.refresh_from_db()
    assert o1.transactions.count() == 1
    assert o1.expires > now()
    assert o1.status == Order.STATUS_PENDING
    assert not o1.require_approval
    assert o1.invoices.count() == 1
    assert len(djmail.outbox) == 1
    assert 'awaiting payment' in djmail.outbox[0].subject
    assert djmail.outbox[0].to == ['dummy@dummy.test']


@pytest.mark.django_db
def test_approve_send_to_attendees(event):
    djmail.outbox = []
    event.settings.invoice_generate = True
    event.settings.mail_send_order_approved_attendee = True
    o1 = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() - timedelta(days=10),
        total=10, require_approval=True, locale='en'
    )
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 default_price=Decimal('23.00'), admission=True)
    OrderPosition.objects.create(
        order=o1, item=ticket, variation=None, price=Decimal("23.00"),
        attendee_name_parts={'full_name': "Peter"}, attendee_email='attendee@dummy.test',
        positionid=1
    )
    o1.create_transactions()
    assert o1.transactions.count() == 0
    approve_order(o1)
    o1.refresh_from_db()
    assert len(djmail.outbox) == 2
    assert djmail.outbox[0].to == ['dummy@dummy.test']
    assert djmail.outbox[1].to == ['attendee@dummy.test']
    assert 'awaiting payment' in djmail.outbox[0].subject
    assert 'awaiting payment' not in djmail.outbox[1].subject


@pytest.mark.django_db
def test_approve_free(event):
    djmail.outbox = []
    event.settings.invoice_generate = True
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
    assert djmail.outbox[0].to == ['dummy@dummy.test']


@pytest.mark.django_db
def test_approve_free_send_to_attendees(event):
    djmail.outbox = []
    event.settings.invoice_generate = True
    event.settings.mail_send_order_approved_free_attendee = True
    o1 = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() - timedelta(days=10),
        total=0, require_approval=True
    )
    ticket = Item.objects.create(event=event, name='Free ticket',
                                 default_price=Decimal('0.00'), admission=True)
    OrderPosition.objects.create(
        order=o1, item=ticket, variation=None, price=Decimal("0.00"),
        attendee_name_parts={'full_name': "Peter"}, attendee_email='attendee@dummy.test',
        positionid=1
    )
    approve_order(o1)
    o1.refresh_from_db()
    assert o1.expires > now()
    assert o1.status == Order.STATUS_PAID
    assert not o1.require_approval
    assert o1.invoices.count() == 0
    assert len(djmail.outbox) == 2
    assert djmail.outbox[0].to == ['dummy@dummy.test']
    assert djmail.outbox[1].to == ['attendee@dummy.test']
    assert 'confirmed' in djmail.outbox[0].subject
    assert 'registration' in djmail.outbox[1].subject


@pytest.mark.django_db
def test_approve_free_after_last_payment_date(event):
    event.settings.payment_term_last = (now() - timedelta(days=1)).date().isoformat()
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
        self.o = Organizer.objects.create(name='Dummy', slug='dummy')
        with scope(organizer=self.o):
            self.event = Event.objects.create(
                organizer=self.o, name='Dummy', slug='dummy',
                date_from=now() + timedelta(days=2),
                plugins='pretix.plugins.banktransfer'
            )
            self.order = Order.objects.create(
                code='FOO', event=self.event, email='dummy@dummy.test',
                status=Order.STATUS_PENDING, locale='en',
                datetime=now() - timedelta(hours=4),
                expires=now() - timedelta(hours=4) + timedelta(days=10),
                total=Decimal('46.00'),
            )
            self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                              default_price=Decimal('23.00'), admission=True)
            self.op1 = OrderPosition.objects.create(
                order=self.order, item=self.ticket, variation=None,
                price=Decimal("23.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
            )
            djmail.outbox = []

    @classscope(attr='o')
    def test_disabled(self):
        send_expiry_warnings(sender=self.event)
        assert len(djmail.outbox) == 0

    @classscope(attr='o')
    def test_sent_once(self):
        self.event.settings.mail_days_order_expire_warning = 12
        send_expiry_warnings(sender=self.event)
        assert len(djmail.outbox) == 1

    @classscope(attr='o')
    def test_paid(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        send_expiry_warnings(sender=self.event)
        assert len(djmail.outbox) == 0

    @classscope(attr='o')
    def test_sent_days(self):
        self.event.settings.mail_days_order_expire_warning = 9
        send_expiry_warnings(sender=self.event)
        assert len(djmail.outbox) == 0
        self.event.settings.mail_days_order_expire_warning = 10
        send_expiry_warnings(sender=self.event)
        assert len(djmail.outbox) == 1
        assert "only guarantee your order" in djmail.outbox[0].body

    @classscope(attr='o')
    def test_sent_no_expiry(self):
        self.order.valid_if_pending = True
        self.order.save()
        self.event.settings.mail_days_order_expire_warning = 10
        send_expiry_warnings(sender=self.event)
        assert len(djmail.outbox) == 1
        assert "only guarantee your order" not in djmail.outbox[0].body
        assert "required to pay" in djmail.outbox[0].body

    @classscope(attr='o')
    def test_sent_not_immediately_after_purchase(self):
        self.order.datetime = now()
        self.order.expires = now() + timedelta(hours=3)
        self.order.save()
        self.event.settings.mail_days_order_expire_warning = 2
        send_expiry_warnings(sender=self.event)
        assert len(djmail.outbox) == 0


class DownloadReminderTests(TestCase):
    def setUp(self):
        super().setUp()
        self.o = Organizer.objects.create(name='Dummy', slug='dummy')
        with scope(organizer=self.o):
            self.event = Event.objects.create(
                organizer=self.o, name='Dummy', slug='dummy',
                date_from=now() + timedelta(days=2),
                plugins='pretix.plugins.banktransfer'
            )
            self.order = Order.objects.create(
                code='FOO', event=self.event, email='dummy@dummy.test',
                status=Order.STATUS_PAID, locale='en',
                datetime=now() - timedelta(days=4),
                expires=now() - timedelta(hours=4) + timedelta(days=10),
                total=Decimal('46.00'),
            )
            self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                              default_price=Decimal('23.00'), admission=True)
            self.op1 = OrderPosition.objects.create(
                order=self.order, item=self.ticket, variation=None,
                price=Decimal("23.00"), attendee_name_parts={"full_name": "Peter"}, positionid=1
            )
            self.event.settings.ticket_download = True
            djmail.outbox = []

    @classscope(attr='o')
    def test_downloads_disabled(self):
        self.event.settings.mail_days_download_reminder = 2
        self.event.settings.ticket_download = False
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 0

    @classscope(attr='o')
    def test_downloads_disabled_per_product(self):
        self.event.settings.mail_days_download_reminder = 2
        self.ticket.generate_tickets = False
        self.ticket.save()
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 0

    @classscope(attr='o')
    def test_disabled(self):
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 0

    @classscope(attr='o')
    def test_sent_once(self):
        self.event.settings.mail_days_download_reminder = 2
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == ['dummy@dummy.test']
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 1

    @classscope(attr='o')
    def test_send_to_attendees(self):
        self.event.settings.mail_send_download_reminder_attendee = True
        self.event.settings.mail_days_download_reminder = 2
        self.op1.attendee_email = 'attendee@dummy.test'
        self.op1.save()
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 2
        assert djmail.outbox[0].to == ['dummy@dummy.test']
        assert djmail.outbox[1].to == ['attendee@dummy.test']
        assert '/ticket/' in djmail.outbox[1].body
        assert '/order/' not in djmail.outbox[1].body

    @classscope(attr='o')
    def test_send_to_attendees_subevent_past(self):
        se1 = self.event.subevents.create(name="Foo", date_from=now() - timedelta(days=2))
        self.op1.subevent = se1
        self.op1.attendee_email = 'attendee@dummy.test'
        self.op1.save()
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 0

    @classscope(attr='o')
    def test_send_to_attendees_subevent_future(self):
        self.event.settings.mail_send_download_reminder_attendee = True
        self.event.settings.mail_days_download_reminder = 2
        se1 = self.event.subevents.create(name="Foo", date_from=now() + timedelta(days=2))
        se2 = self.event.subevents.create(name="Foo", date_from=now() + timedelta(days=8))
        self.op1.subevent = se1
        self.op1.attendee_email = 'attendee@dummy.test'
        self.op1.save()
        self.op2 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None, subevent=se2, attendee_email="attendee2@dummy.test",
            price=Decimal("23.00"), attendee_name_parts={"full_name": "Peter"}, positionid=1
        )
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 2
        assert djmail.outbox[0].to == ['dummy@dummy.test']
        assert djmail.outbox[1].to == ['attendee@dummy.test']

    @classscope(attr='o')
    def test_send_not_to_attendees_with_same_address(self):
        self.event.settings.mail_send_download_reminder_attendee = True
        self.event.settings.mail_days_download_reminder = 2
        self.op1.attendee_email = 'dummy@dummy.test'
        self.op1.save()
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == ['dummy@dummy.test']
        assert '/order/' in djmail.outbox[0].body

    @classscope(attr='o')
    def test_sent_paid_only(self):
        self.event.settings.mail_days_download_reminder = 2
        self.order.status = Order.STATUS_PENDING
        self.order.save()
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 0

    @classscope(attr='o')
    def test_not_sent_too_early(self):
        self.event.settings.mail_days_download_reminder = 1
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 0

    @classscope(attr='o')
    def test_not_sent_too_soon_after_purchase(self):
        self.order.datetime = now()
        self.order.save()
        self.event.settings.mail_days_download_reminder = 2
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 0

    @classscope(attr='o')
    def test_not_sent_after_reminder_date(self):
        self.order.datetime = self.event.date_from - timedelta(days=1)
        self.order.save()
        self.event.settings.mail_days_download_reminder = 2
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 0

    @classscope(attr='o')
    def test_not_sent_for_disabled_sales_channel(self):
        self.event.settings.mail_days_download_reminder = 2
        self.event.settings.mail_sales_channel_download_reminder = []
        send_download_reminders(sender=self.event)
        assert len(djmail.outbox) == 0


class OrderCancelTests(TestCase):
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
            self.order.create_transactions()
            generate_invoice(self.order)
            djmail.outbox = []

    @classscope(attr='o')
    def test_cancel_canceled(self):
        self.order.status = Order.STATUS_CANCELED
        self.order.save()
        with pytest.raises(OrderError):
            cancel_order(self.order.pk)

    @classscope(attr='o')
    def test_cancel_send_mail(self):
        cancel_order(self.order.pk, send_mail=True)
        assert len(djmail.outbox) == 1

    @classscope(attr='o')
    def test_cancel_send_no_mail(self):
        cancel_order(self.order.pk, send_mail=False)
        assert len(djmail.outbox) == 0

    @classscope(attr='o')
    def test_cancel_unpaid(self):
        cancel_order(self.order.pk)
        self.order.refresh_from_db()
        assert self.order.cancellation_date
        assert self.order.status == Order.STATUS_CANCELED
        assert self.order.all_logentries().last().action_type == 'pretix.event.order.canceled'
        assert self.order.invoices.count() == 2

    @classscope(attr='o')
    def test_cancel_unpaid_with_voucher(self):
        self.op1.voucher = self.event.vouchers.create(item=self.ticket, redeemed=1)
        self.op1.save()
        cancel_order(self.order.pk)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_CANCELED
        assert self.order.all_logentries().last().action_type == 'pretix.event.order.canceled'
        self.op1.voucher.refresh_from_db()
        assert self.op1.voucher.redeemed == 0
        assert self.order.invoices.count() == 2

    @classscope(attr='o')
    def test_cancel_paid(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        cancel_order(self.order.pk)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_CANCELED
        assert self.order.all_logentries().last().action_type == 'pretix.event.order.canceled'
        assert self.order.invoices.count() == 2
        assert self.order.transactions.count() == 4
        assert self.order.transactions.aggregate(s=Sum(F('price') * F('count')))['s'] == Decimal('0.00')

    @classscope(attr='o')
    def test_cancel_paid_with_too_high_fee(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.order.payments.create(state=OrderPayment.PAYMENT_STATE_CONFIRMED, amount=48.5)
        with pytest.raises(OrderError):
            cancel_order(self.order.pk, cancellation_fee=50)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID
        assert self.order.total == 46

    @classscope(attr='o')
    def test_cancel_paid_with_fee(self):
        f = self.order.fees.create(fee_type=OrderFee.FEE_TYPE_SHIPPING, value=2.5)
        self.order.status = Order.STATUS_PAID
        self.order.total = 48.5
        self.order.save()
        self.order.payments.create(state=OrderPayment.PAYMENT_STATE_CONFIRMED, amount=48.5)
        self.op1.voucher = self.event.vouchers.create(item=self.ticket, redeemed=1)
        self.op1.save()
        cancel_order(self.order.pk, cancellation_fee=2.5)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID
        self.op1.refresh_from_db()
        assert self.op1.canceled
        self.op2.refresh_from_db()
        assert self.op2.canceled
        f.refresh_from_db()
        assert f.canceled
        assert self.order.total == 2.5
        assert self.order.all_logentries().last().action_type == 'pretix.event.order.canceled'
        self.op1.voucher.refresh_from_db()
        assert self.op1.voucher.redeemed == 0
        assert self.order.invoices.count() == 3
        assert not self.order.invoices.last().is_cancellation

    @classscope(attr='o')
    def test_cancel_paid_with_fee_change_secret(self):
        self.event.settings.ticket_secret_generator = "pretix_sig1"
        s = self.op1.secret
        self.order.fees.create(fee_type=OrderFee.FEE_TYPE_SHIPPING, value=2.5)
        self.order.status = Order.STATUS_PAID
        self.order.total = 48.5
        self.order.save()
        self.order.payments.create(state=OrderPayment.PAYMENT_STATE_CONFIRMED, amount=48.5)
        self.op1.voucher = self.event.vouchers.create(item=self.ticket, redeemed=1)
        self.op1.save()
        cancel_order(self.order.pk, cancellation_fee=2.5)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID
        self.op1.refresh_from_db()
        assert self.op1.canceled
        assert self.op1.secret != s

    @classscope(attr='o')
    def test_auto_refund_possible(self):
        p1 = self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='testdummy_partialrefund'
        )
        cancel_order(self.order.pk, cancellation_fee=2, try_auto_refund=True)
        r = self.order.refunds.get()
        assert r.state == OrderRefund.REFUND_STATE_DONE
        assert r.amount == Decimal('44.00')
        assert r.source == OrderRefund.REFUND_SOURCE_BUYER
        assert r.payment == p1
        assert self.order.all_logentries().filter(action_type='pretix.event.order.refund.created').exists()
        assert not self.order.all_logentries().filter(action_type='pretix.event.order.refund.requested').exists()

    @classscope(attr='o')
    def test_auto_refund_possible_giftcard(self):
        gc = self.o.issued_gift_cards.create(currency="EUR")
        p1 = self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='giftcard',
            info='{"gift_card": %d}' % gc.pk
        )
        cancel_order(self.order.pk, cancellation_fee=2, try_auto_refund=True)
        r = self.order.refunds.get()
        assert r.state == OrderRefund.REFUND_STATE_DONE
        assert r.amount == Decimal('44.00')
        assert r.source == OrderRefund.REFUND_SOURCE_BUYER
        assert r.payment == p1
        assert self.order.all_logentries().filter(action_type='pretix.event.order.refund.created').exists()
        assert not self.order.all_logentries().filter(action_type='pretix.event.order.refund.requested').exists()
        assert gc.value == Decimal('44.00')

    @classscope(attr='o')
    def test_auto_refund_possible_issued_giftcard(self):
        gc = self.o.issued_gift_cards.create(currency="EUR", issued_in=self.op1)
        gc.transactions.create(value=23, acceptor=self.o)
        self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='testdummy_partialrefund'
        )
        cancel_order(self.order.pk, cancellation_fee=2, try_auto_refund=True)
        r = self.order.refunds.get()
        assert r.state == OrderRefund.REFUND_STATE_DONE
        assert gc.value == Decimal('0.00')

    @classscope(attr='o')
    def test_auto_refund_impossible_issued_giftcard_used(self):
        gc = self.o.issued_gift_cards.create(currency="EUR", issued_in=self.op1)
        gc.transactions.create(value=20, acceptor=self.o)
        self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='testdummy_partialrefund'
        )
        with pytest.raises(OrderError):
            cancel_order(self.order.pk, cancellation_fee=2, try_auto_refund=True)
        assert gc.value == Decimal('20.00')

    @classscope(attr='o')
    def test_auto_refund_impossible(self):
        self.order.payments.create(
            amount=Decimal('46.00'),
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider='testdummy_fullrefund'
        )
        cancel_order(self.order.pk, cancellation_fee=2, try_auto_refund=True)
        assert not self.order.refunds.exists()
        assert self.order.all_logentries().filter(action_type='pretix.event.order.refund.requested').exists()


class OrderChangeManagerTests(TestCase):
    def setUp(self):
        super().setUp()
        self.o = Organizer.objects.create(name='Dummy', slug='dummy')
        with scope(organizer=self.o):
            self.event = Event.objects.create(organizer=self.o, name='Dummy', slug='dummy', date_from=now(),
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
            self.order.create_transactions(is_new=True)
            assert self.order.transactions.count() == 2
            self.ocm = OrderChangeManager(self.order, None)
            self.quota = self.event.quotas.create(name='Test', size=None)
            self.quota.items.add(self.ticket)
            self.quota.items.add(self.ticket2)
            self.quota.items.add(self.shirt)

            self.mtype = self.o.membership_types.create(name="Week pass")
            self.vip = Item.objects.create(event=self.event, name='VIP', tax_rule=self.tr7,
                                           default_price=Decimal('23.00'), admission=True,
                                           require_membership=True)
            self.vip.require_membership_types.add(self.mtype)
            self.quota.items.add(self.vip)
            self.stalls = Item.objects.create(event=self.event, name='Stalls', tax_rule=self.tr7,
                                              default_price=Decimal('23.00'), admission=True)
            self.stalls = Item.objects.create(event=self.event, name='Stalls', tax_rule=self.tr7,
                                              default_price=Decimal('23.00'), admission=True)
            self.plan = SeatingPlan.objects.create(
                name="Plan", organizer=self.o, layout="{}"
            )
            self.event.seat_category_mappings.create(
                layout_category='Stalls', product=self.stalls
            )
            self.quota.items.add(self.stalls)
            self.seat_a1 = self.event.seats.create(seat_number="A1", product=self.stalls, seat_guid="A1")
            self.seat_a2 = self.event.seats.create(seat_number="A2", product=self.stalls, seat_guid="A2")
            self.seat_a3 = self.event.seats.create(seat_number="A3", product=self.stalls, seat_guid="A3")

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

    @classscope(attr='o')
    def test_multiple_commits_forbidden(self):
        self.ocm.change_price(self.op1, Decimal('10.00'))
        self.ocm.commit()
        self.ocm.change_price(self.op1, Decimal('42.00'))
        with self.assertRaises(OrderError):
            self.ocm.commit()

    @classscope(attr='o')
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

    @classscope(attr='o')
    def test_change_subevent_and_product(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        se2 = self.event.subevents.create(name="Bar", date_from=now())
        self.op1.subevent = se1
        self.op1.save()
        self.quota.subevent = se1
        self.quota.save()
        self.quota.items.remove(self.shirt)
        q2 = self.event.quotas.create(name="Q2", size=None, subevent=se2)
        q2.items.add(self.shirt)
        self.ocm.change_item_and_subevent(self.op1, self.shirt, None, se2)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.subevent == se2
        assert self.op1.item == self.shirt
        assert self.order.transactions.count() == 4

    @classscope(attr='o')
    def test_change_subevent_success(self):
        self.event.has_subevents = True
        self.event.save()
        s = self.op1.secret
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
        assert self.op1.price == Decimal('23.00')
        assert self.order.total == self.op1.price + self.op2.price
        assert self.op1.secret == s
        assert self.order.transactions.count() == 4

    @classscope(attr='o')
    def test_change_subevent_success_change_secret(self):
        self.event.settings.ticket_secret_generator = "pretix_sig1"
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        se2 = self.event.subevents.create(name="Bar", date_from=now())
        SubEventItem.objects.create(subevent=se2, item=self.ticket, price=12)
        s = self.op1.secret
        self.op1.subevent = se1
        self.op1.save()
        self.quota.subevent = se2
        self.quota.save()

        self.ocm.change_subevent(self.op1, se2)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.subevent == se2
        assert self.op1.price == Decimal('23.00')
        assert self.order.total == self.op1.price + self.op2.price
        assert self.op1.secret != s
        assert self.order.transactions.count() == 4

    @classscope(attr='o')
    def test_change_subevent_with_price_success(self):
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
        self.ocm.change_price(self.op1, Decimal('12.00'))
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.subevent == se2
        assert self.op1.price == Decimal('12.00')
        assert self.order.total == self.op1.price + self.op2.price
        assert self.order.transactions.count() == 4

    @classscope(attr='o')
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
        assert self.order.transactions.count() == 2

    @classscope(attr='o')
    def test_change_item_quota_required(self):
        self.quota.delete()
        with self.assertRaises(OrderError):
            self.ocm.change_item(self.op1, self.shirt, None)

    @classscope(attr='o')
    def test_change_new_secret_by_scheme(self):
        self.event.settings.ticket_secret_generator = "pretix_sig1"
        s = self.op1.secret
        p = self.op1.price
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.shirt
        assert self.op1.price == p
        assert self.op1.tax_value == Decimal('3.67')
        assert self.op1.tax_rule == self.shirt.tax_rule
        assert self.op1.secret != s
        assert self.order.transactions.count() == 4

    @classscope(attr='o')
    def test_change_item_keep_price(self):
        p = self.op1.price
        s = self.op1.secret
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.shirt
        assert self.op1.price == p
        assert self.op1.tax_value == Decimal('3.67')
        assert self.op1.tax_rule == self.shirt.tax_rule
        assert self.op1.secret == s
        assert self.order.transactions.count() == 4

    @classscope(attr='o')
    def test_change_item_change_voucher_budget_use(self):
        self.op1.voucher = self.event.vouchers.create(item=self.shirt, redeemed=1, price_mode='set', value='5.00')
        self.op1.price = Decimal('5.00')
        self.op1.voucher_budget_use = Decimal('18.00')
        self.op1.save()
        p = self.op1.price
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.shirt
        assert self.op1.price == p
        assert self.op1.voucher_budget_use == Decimal('7.00')

    @classscope(attr='o')
    def test_change_item_change_voucher_budget_use_minimum_value(self):
        self.op1.voucher = self.event.vouchers.create(item=self.shirt, redeemed=1, price_mode='set', value='20.00')
        self.op1.price = Decimal('20.00')
        self.op1.voucher_budget_use = Decimal('3.00')
        self.op1.save()
        p = self.op1.price
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.shirt
        assert self.op1.price == p
        assert self.op1.voucher_budget_use == Decimal('0.00')

    @classscope(attr='o')
    def test_change_item_success(self):
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.shirt
        assert self.op1.price == Decimal('23.00')
        assert self.op1.tax_rate == self.shirt.tax_rule.rate
        assert round_decimal(self.op1.price * (1 - 100 / (100 + self.op1.tax_rate))) == self.op1.tax_value
        assert self.order.total == self.op1.price + self.op2.price

    @classscope(attr='o')
    def test_change_item_with_price_success(self):
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.change_price(self.op1, Decimal('12.00'))
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.shirt
        assert self.op1.price == Decimal('12.00')
        assert self.op1.tax_rate == self.shirt.tax_rule.rate
        assert round_decimal(self.op1.price * (1 - 100 / (100 + self.op1.tax_rate))) == self.op1.tax_value
        assert self.order.total == self.op1.price + self.op2.price

        t0 = self.order.transactions.filter(positionid=self.op1.positionid)[0]
        assert t0.item == self.ticket
        assert t0.price == Decimal('23.00')
        assert t0.count == 1
        t1 = self.order.transactions.filter(positionid=self.op1.positionid)[1]
        assert t1.item == self.ticket
        assert t1.price == Decimal('23.00')
        assert t1.count == -1
        t2 = self.order.transactions.filter(positionid=self.op1.positionid)[2]
        assert t2.item == self.shirt
        assert t2.price == Decimal('12.00')
        assert t2.count == 1

    @classscope(attr='o')
    def test_change_price_success(self):
        self.ocm.change_price(self.op1, Decimal('24.00'))
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.ticket
        assert self.op1.price == Decimal('24.00')
        assert round_decimal(self.op1.price * (1 - 100 / (100 + self.op1.tax_rate))) == self.op1.tax_value
        assert self.order.total == self.op1.price + self.op2.price

    @classscope(attr='o')
    def test_change_price_net_success(self):
        self.tr7.price_includes_tax = False
        self.tr7.save()
        self.ocm.change_price(self.op1, Decimal('10.70'))
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.ticket
        assert self.op1.price == Decimal('10.70')
        assert round_decimal(self.op1.price * (1 - 100 / (100 + self.op1.tax_rate))) == self.op1.tax_value
        assert self.order.total == self.op1.price + self.op2.price

    @classscope(attr='o')
    def test_cancel_success(self):
        s = self.op1.secret
        self.ocm.cancel(self.op1)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 1
        assert self.order.total == self.op2.price
        self.op1.refresh_from_db()
        assert self.op1.canceled
        assert self.op1.secret == s
        assert self.order.transactions.count() == 3

    @classscope(attr='o')
    def test_cancel_success_changed_secret(self):
        self.event.settings.ticket_secret_generator = "pretix_sig1"
        s = self.op1.secret
        self.ocm.cancel(self.op1)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 1
        assert self.order.total == self.op2.price
        self.op1.refresh_from_db()
        assert self.op1.canceled
        assert self.op1.secret != s

    @classscope(attr='o')
    def test_cancel_with_addon(self):
        self.shirt.category = self.event.categories.create(name='Add-ons', is_addon=True)
        self.ticket.addons.create(addon_category=self.shirt.category)
        self.ocm.add_position(self.shirt, None, Decimal('13.00'), self.op1)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.ocm = OrderChangeManager(self.order, None)
        assert self.order.positions.count() == 3

        self.ocm.cancel(self.op1)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 1
        assert self.order.total == self.op2.price
        self.op1.refresh_from_db()
        assert self.op1.canceled
        assert self.op1.addons.first().canceled

    @classscope(attr='o')
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

    @classscope(attr='o')
    def test_cancel_issued_giftcard(self):
        gc = self.o.issued_gift_cards.create(currency="EUR", issued_in=self.op1)
        gc.transactions.create(value=23, acceptor=self.o)
        self.ocm.cancel(self.op1)
        self.ocm.commit()
        assert gc.value == Decimal('0.00')

    @classscope(attr='o')
    def test_cancel_issued_membership(self):
        mt = self.event.organizer.membership_types.create(name="foo")
        customer = self.event.organizer.customers.create()
        self.order.customer = customer
        self.o.save()
        m = customer.memberships.create(
            membership_type=mt,
            date_start=now(),
            date_end=now(),
            granted_in=self.order.positions.first(),
        )
        self.ocm.cancel(self.op1)
        self.ocm.commit()
        m.refresh_from_db()
        assert m.canceled

    @classscope(attr='o')
    def test_cancel_issued_giftcard_used(self):
        gc = self.o.issued_gift_cards.create(currency="EUR", issued_in=self.op1)
        gc.transactions.create(value=20, acceptor=self.o)
        self.ocm.cancel(self.op1)
        with self.assertRaises(OrderError):
            self.ocm.commit()

    @classscope(attr='o')
    def test_change_price_issued_giftcard_used(self):
        gc = self.o.issued_gift_cards.create(currency="EUR", issued_in=self.op1)
        gc.transactions.create(value=20, acceptor=self.o)
        with self.assertRaises(OrderError):
            self.ocm.change_price(self.op1, 25)

    @classscope(attr='o')
    def test_cancel_all_in_order(self):
        self.ocm.cancel(self.op1)
        self.ocm.cancel(self.op2)
        with self.assertRaises(OrderError):
            self.ocm.commit()
        assert self.order.positions.count() == 2

    @classscope(attr='o')
    def test_empty(self):
        self.ocm.commit()

    @classscope(attr='o')
    def test_quota_unlimited(self):
        q = self.event.quotas.create(name='Test', size=None)
        q.items.add(self.shirt)
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.item == self.shirt

    @classscope(attr='o')
    def test_quota_full(self):
        q = self.event.quotas.create(name='Test', size=0)
        q.items.add(self.shirt)
        self.ocm.change_item(self.op1, self.shirt, None)
        with self.assertRaises(OrderError):
            self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.item == self.ticket

    @classscope(attr='o')
    def test_quota_ignore(self):
        q = self.event.quotas.create(name='Test', size=0)
        q.items.add(self.shirt)
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit(check_quotas=False)
        self.op1.refresh_from_db()
        assert self.op1.item == self.shirt

    @classscope(attr='o')
    def test_quota_full_but_in_same(self):
        q = self.event.quotas.create(name='Test', size=0)
        q.items.add(self.shirt)
        q.items.add(self.ticket)
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.item == self.shirt

    @classscope(attr='o')
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

    @classscope(attr='o')
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

    @classscope(attr='o')
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
        assert self.order.transactions.count() == 6

    @classscope(attr='o')
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

    @classscope(attr='o')
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

    @classscope(attr='o')
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

    @classscope(attr='o')
    def test_require_pending(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.item == self.shirt

    @classscope(attr='o')
    def test_change_price_to_free_marked_as_paid(self):
        self.ocm.change_price(self.op1, Decimal('0.00'))
        self.ocm.change_price(self.op2, Decimal('0.00'))
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == 0
        assert self.order.status == Order.STATUS_PAID
        assert self.order.payments.last().provider == 'free'

    @classscope(attr='o')
    def test_change_price_to_free_require_approval(self):
        self.order.require_approval = True
        self.order.save()
        self.ocm = OrderChangeManager(self.order, None)
        self.ocm.change_price(self.op1, Decimal('0.00'))
        self.ocm.change_price(self.op2, Decimal('0.00'))
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == 0
        assert self.order.status == Order.STATUS_PENDING

    @classscope(attr='o')
    def test_change_paid_same_price(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.ocm.change_item(self.op1, self.ticket2, None)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == 46
        assert self.order.status == Order.STATUS_PAID

    @classscope(attr='o')
    def test_change_paid_different_price(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.ocm.change_price(self.op1, Decimal('5.00'))
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('28.00')
        assert self.order.status == Order.STATUS_PAID

    @classscope(attr='o')
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
        assert self.order.transactions.count() == 4

    @classscope(attr='o')
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

    @classscope(attr='o')
    def test_add_item_quota_required(self):
        self.quota.delete()
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.shirt, None, None, None)

    @classscope(attr='o')
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
        assert self.order.transactions.count() == 3

    @classscope(attr='o')
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

    @classscope(attr='o')
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

    @classscope(attr='o')
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

    @classscope(attr='o')
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

    @classscope(attr='o')
    def test_add_item_quota_full(self):
        q1 = self.event.quotas.create(name='Test', size=0)
        q1.items.add(self.shirt)
        self.ocm.add_position(self.shirt, None, None, None)
        with self.assertRaises(OrderError):
            self.ocm.commit()
        assert self.order.positions.count() == 2

    @classscope(attr='o')
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

    @classscope(attr='o')
    def test_add_item_addon_is_bundle(self):
        self.shirt.category = self.event.categories.create(name='Add-ons', is_addon=True)
        self.ticket.bundles.create(bundled_item=self.shirt)
        self.ocm.add_position(self.shirt, None, Decimal('13.00'), self.op1)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.positions.count() == 3
        nop = self.order.positions.last()
        assert nop.item == self.shirt
        assert nop.addon_to == self.op1
        assert nop.is_bundled

    @classscope(attr='o')
    def test_add_item_addon_invalid(self):
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.shirt, None, Decimal('13.00'), self.op1)
        self.shirt.category = self.event.categories.create(name='Add-ons', is_addon=True)
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.shirt, None, Decimal('13.00'), None)

    @classscope(attr='o')
    def test_add_item_subevent_required(self):
        self.event.has_subevents = True
        self.event.save()
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.ticket, None, None, None)

    @classscope(attr='o')
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

    @classscope(attr='o')
    def test_reissue_invoice(self):
        generate_invoice(self.order)
        assert self.order.invoices.count() == 1
        self.ocm.add_position(self.ticket, None, Decimal('0.00'))
        self.ocm.commit()
        assert self.order.invoices.count() == 3

    @classscope(attr='o')
    def test_reissue_invoice_after_tax_change(self):
        generate_invoice(self.order)
        self.tr7.rate = Decimal('18.00')
        self.tr7.save()
        assert self.order.invoices.count() == 1
        self.ocm.recalculate_taxes(keep='gross')
        print(self.ocm._operations)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.invoices.count() == 3
        new_inv = self.order.invoices.get(is_cancellation=False, refered__isnull=True)
        assert new_inv.lines.first().tax_rate == Decimal('18.00')

    @classscope(attr='o')
    def test_no_new_invoice_for_free_order(self):
        generate_invoice(self.order)
        assert self.order.invoices.count() == 1
        self.ocm.change_price(self.op1, Decimal('0.00'))
        self.ocm.change_price(self.op2, Decimal('0.00'))
        self.ocm.commit()
        assert self.order.invoices.count() == 2

    @classscope(attr='o')
    def test_reissue_invoice_disabled(self):
        self.ocm.reissue_invoice = False
        generate_invoice(self.order)
        assert self.order.invoices.count() == 1
        self.ocm.add_position(self.ticket, None, Decimal('0.00'))
        self.ocm.commit()
        assert self.order.invoices.count() == 1

    @classscope(attr='o')
    def test_dont_reissue_invoice_on_free_product_changes(self):
        self.event.settings.invoice_include_free = False
        generate_invoice(self.order)
        assert self.order.invoices.count() == 1
        self.ocm.add_position(self.ticket, None, Decimal('0.00'))
        self.ocm.commit()
        assert self.order.invoices.count() == 1

    @classscope(attr='o')
    def test_recalculate_country_rate(self):
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

        self._enable_reverse_charge()
        self.tr7.custom_rules = json.dumps([
            {'country': 'AT', 'address_type': '', 'action': 'vat', 'rate': '100.00'}
        ])
        self.tr7.save()

        self.ocm.recalculate_taxes(keep='net')
        self.ocm.commit()
        ops = list(self.order.positions.all())
        for op in ops:
            assert op.price == Decimal('43.00')
            assert op.tax_value == Decimal('21.50')
            assert op.tax_rate == Decimal('100.00')

        assert self.order.total == Decimal('86.00') + fee.value
        assert self.order.transactions.count() == 7

    @classscope(attr='o')
    def test_recalculate_country_rate_keep_gross(self):
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

        self._enable_reverse_charge()
        self.tr7.custom_rules = json.dumps([
            {'country': 'AT', 'address_type': '', 'action': 'vat', 'rate': '100.00'}
        ])
        self.tr7.save()

        self.ocm.recalculate_taxes(keep='gross')
        self.ocm.commit()
        ops = list(self.order.positions.all())
        for op in ops:
            assert op.price == Decimal('23.00')
            assert op.tax_value == Decimal('11.50')
            assert op.tax_rate == Decimal('100.00')

        assert self.order.total == Decimal('46.00') + fee.value

    @classscope(attr='o')
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
            assert op.price == Decimal('23.01')  # sic. we can't really avoid it.
            assert op.tax_value == Decimal('1.51')
            assert op.tax_rate == Decimal('7.00')

        assert self.order.total == Decimal('46.32')
        fee = self.order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
        assert fee.value == prov.calculate_fee(self.order.total)
        assert fee.tax_rate == Decimal('19.00')
        assert fee.tax_value == Decimal('0.05')

    @classscope(attr='o')
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

    @classscope(attr='o')
    def test_split_include_addons(self):
        self.shirt.category = self.event.categories.create(name='Add-ons', is_addon=True)
        self.ticket.addons.create(addon_category=self.shirt.category)
        self.ocm.add_position(self.shirt, None, Decimal('13.00'), self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.ocm = OrderChangeManager(self.order, None)
        a = self.order.positions.get(addon_to=self.op2)

        old_secret = self.op2.secret
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()
        a.refresh_from_db()
        assert self.order.total == Decimal('23.00')
        assert self.order.positions.count() == 1
        assert self.op2.order != self.order
        o2 = self.op2.order
        assert o2.total == Decimal('36.00')
        assert o2.positions.count() == 2
        assert o2.code != self.order.code
        assert o2.secret != self.order.secret
        assert o2.datetime > self.order.datetime
        assert a.addon_to == self.op2
        assert a.order == o2
        assert self.op2.secret != old_secret
        assert not self.order.invoices.exists()
        assert not o2.invoices.exists()

    @classscope(attr='o')
    def test_split_require_approval(self):
        self.op2.item.require_approval = True
        self.op2.item.save()
        self.order.require_approval = True
        self.order.save()
        old_secret = self.op2.secret
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()
        assert self.order.total == Decimal('23.00')
        assert self.order.positions.count() == 1
        assert self.op2.order != self.order
        assert self.op2.order.require_approval
        o2 = self.op2.order
        assert o2.total == Decimal('23.00')
        assert o2.positions.count() == 1
        assert o2.code != self.order.code
        assert o2.secret != self.order.secret
        assert o2.datetime > self.order.datetime
        assert self.op2.secret != old_secret
        assert not self.order.invoices.exists()
        assert not o2.invoices.exists()

    @classscope(attr='o')
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

    @classscope(attr='o')
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

    @classscope(attr='o')
    def test_split_and_change_higher(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.order.payments.create(
            provider='manual',
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            amount=self.order.total,
        )

        # Split
        self.ocm.change_price(self.op2, Decimal('42.00'))
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()

        # First order
        assert self.order.total == Decimal('23.00')
        assert not self.order.fees.exists()
        assert self.order.status == Order.STATUS_PAID
        assert self.order.pending_sum == Decimal('0.00')
        r = self.order.refunds.last()
        assert r.provider == 'offsetting'
        assert r.amount == Decimal('23.00')
        assert r.state == OrderRefund.REFUND_STATE_DONE

        # New order
        assert self.op2.order != self.order
        o2 = self.op2.order
        assert o2.total == Decimal('42.00')
        assert o2.status == Order.STATUS_PENDING
        assert o2.positions.count() == 1
        assert o2.fees.count() == 0
        assert o2.pending_sum == Decimal('19.00')
        p = o2.payments.last()
        assert p.provider == 'offsetting'
        assert p.amount == Decimal('23.00')
        assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED

    @classscope(attr='o')
    def test_split_and_change_lower(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.order.payments.create(
            provider='manual',
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            amount=self.order.total,
        )

        # Split
        self.ocm.change_price(self.op2, Decimal('10.00'))
        self.ocm.split(self.op2)
        self.ocm.commit()
        self.order.refresh_from_db()
        self.op2.refresh_from_db()

        # First order
        assert self.order.total == Decimal('23.00')
        assert not self.order.fees.exists()
        assert self.order.status == Order.STATUS_PAID
        assert self.order.pending_sum == Decimal('-13.00')
        r = self.order.refunds.last()
        assert r.provider == 'offsetting'
        assert r.amount == Decimal('10.00')
        assert r.state == OrderRefund.REFUND_STATE_DONE

        # New order
        assert self.op2.order != self.order
        o2 = self.op2.order
        assert o2.total == Decimal('10.00')
        assert o2.status == Order.STATUS_PAID
        assert o2.positions.count() == 1
        assert o2.fees.count() == 0
        assert o2.pending_sum == Decimal('0.00')
        p = o2.payments.last()
        assert p.provider == 'offsetting'
        assert p.amount == Decimal('10.00')
        assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED

    @classscope(attr='o')
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

    @classscope(attr='o')
    def test_change_price_of_pending_order_with_payment(self):
        self.order.status = Order.STATUS_PENDING
        self.order.save()
        assert self.order.payments.last().state == OrderPayment.PAYMENT_STATE_CREATED
        assert self.order.payments.last().amount == Decimal('46.00')

        self.ocm.change_price(self.op1, Decimal('27.00'))
        self.ocm.commit()

        assert self.order.payments.last().state == OrderPayment.PAYMENT_STATE_CANCELED
        assert self.order.payments.last().amount == Decimal('46.00')

    @classscope(attr='o')
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

    @classscope(attr='o')
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

    @classscope(attr='o')
    def test_split_to_empty(self):
        self.ocm.split(self.op1)
        self.ocm.split(self.op2)
        with self.assertRaises(OrderError):
            self.ocm.commit()

    @classscope(attr='o')
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

    @classscope(attr='o')
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

    @classscope(attr='o')
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

    @classscope(attr='o')
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

    @classscope(attr='o')
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

    @classscope(attr='o')
    def test_change_seat_circular(self):
        self.op1.seat = self.seat_a1
        self.op1.save()
        self.op2.seat = self.seat_a2
        self.op2.save()
        self.ocm.change_seat(self.op1, self.seat_a2)
        self.ocm.change_seat(self.op2, self.seat_a1)
        self.ocm.commit()
        self.op1.refresh_from_db()
        self.op2.refresh_from_db()
        assert self.op1.seat == self.seat_a2
        assert self.op2.seat == self.seat_a1

    @classscope(attr='o')
    def test_change_seat_duplicate(self):
        self.op1.seat = self.seat_a1
        self.op1.save()
        self.op2.seat = self.seat_a2
        self.op2.save()
        self.ocm.change_seat(self.op1, self.seat_a2)
        with self.assertRaises(OrderError):
            self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.seat == self.seat_a1

    @classscope(attr='o')
    def test_change_seat_and_cancel(self):
        self.op1.seat = self.seat_a1
        self.op1.save()
        self.op2.seat = self.seat_a2
        self.op2.save()
        self.ocm.change_seat(self.op1, self.seat_a2)
        self.ocm.cancel(self.op2)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.seat == self.seat_a2

    @classscope(attr='o')
    def test_change_seat(self):
        self.op1.seat = self.seat_a1
        self.op1.save()
        self.ocm.change_seat(self.op1, self.seat_a2)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.seat == self.seat_a2

    @classscope(attr='o')
    def test_change_add_seat(self):
        # does this make sense or do we block it based on the item? this is currently not reachable through the UI
        self.ocm.change_seat(self.op1, self.seat_a1)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.seat == self.seat_a1

    @classscope(attr='o')
    def test_remove_seat(self):
        # does this make sense or do we block it based on the item? this is currently not reachable through the UI
        self.op1.seat = self.seat_a1
        self.op1.save()
        self.ocm.change_seat(self.op1, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.seat is None

    @classscope(attr='o')
    def test_add_with_seat(self):
        self.ocm.add_position(self.stalls, None, price=Decimal('13.00'), seat=self.seat_a3)
        self.ocm.commit()
        op3 = self.order.positions.last()
        assert op3.item == self.stalls
        assert op3.seat == self.seat_a3

    @classscope(attr='o')
    def test_add_with_taken_seat(self):
        self.op1.seat = self.seat_a1
        self.op1.save()
        self.ocm.add_position(self.stalls, None, price=Decimal('13.00'), seat=self.seat_a1)
        with self.assertRaises(OrderError):
            self.ocm.commit()

    @classscope(attr='o')
    def test_add_with_seat_not_required_if_no_choice(self):
        self.event.settings.seating_choice = False
        self.ocm.add_position(self.stalls, None, price=Decimal('13.00'))

    @classscope(attr='o')
    def test_add_with_seat_not_required(self):
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.stalls, None, price=Decimal('13.00'))

    @classscope(attr='o')
    def test_add_with_seat_forbidden(self):
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.ticket, None, price=Decimal('13.00'), seat=self.seat_a1)

    @classscope(attr='o')
    def test_add_with_seat_blocked(self):
        self.seat_a1.blocked = True
        self.seat_a1.save()
        self.ocm.add_position(self.stalls, None, price=Decimal('13.00'), seat=self.seat_a1)
        with self.assertRaises(OrderError):
            self.ocm.commit()

    @classscope(attr='o')
    def test_change_seat_to_blocked(self):
        self.seat_a2.blocked = True
        self.seat_a2.save()
        self.op1.seat = self.seat_a1
        self.op1.save()
        self.ocm.change_seat(self.op1, self.seat_a2)
        with self.assertRaises(OrderError):
            self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.seat == self.seat_a1

    @classscope(attr='o')
    def test_change_seat_require_subevent_change(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        se2 = self.event.subevents.create(name="Bar", date_from=now())
        self.op1.subevent = se1
        self.op1.seat = self.seat_a1
        self.op1.save()
        self.quota.subevent = se2
        self.quota.save()
        self.seat_a1.subevent = se1
        self.seat_a1.save()
        self.seat_a2.subevent = se2
        self.seat_a2.save()
        self.ocm.change_seat(self.op1, self.seat_a2)
        with self.assertRaises(OrderError):
            self.ocm.commit()

    @classscope(attr='o')
    def test_change_subevent_require_seat_change(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        se2 = self.event.subevents.create(name="Bar", date_from=now())
        self.op1.subevent = se1
        self.op1.seat = self.seat_a1
        self.op1.save()
        self.quota.subevent = se2
        self.quota.save()
        self.seat_a1.subevent = se1
        self.seat_a1.save()
        self.seat_a2.subevent = se2
        self.seat_a2.save()
        self.ocm.change_subevent(self.op1, se2)
        with self.assertRaises(OrderError):
            self.ocm.commit()

    @classscope(attr='o')
    def test_change_subevent_and_seat(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        se2 = self.event.subevents.create(name="Bar", date_from=now())
        self.op1.subevent = se1
        self.op1.seat = self.seat_a1
        self.op1.save()
        self.quota.subevent = se2
        self.quota.save()
        self.seat_a1.subevent = se1
        self.seat_a1.save()
        self.seat_a2.subevent = se2
        self.seat_a2.save()
        self.ocm.change_subevent(self.op1, se2)
        self.ocm.change_seat(self.op1, self.seat_a2)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.seat == self.seat_a2
        assert self.op1.subevent == se2

    @classscope(attr='o')
    def test_change_seat_inside_subevent(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        self.op1.subevent = se1
        self.op1.seat = self.seat_a1
        self.op1.save()
        self.seat_a1.subevent = se1
        self.seat_a1.save()
        self.seat_a2.subevent = se1
        self.seat_a2.save()
        self.ocm.change_seat(self.op1, self.seat_a2)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.seat == self.seat_a2
        assert self.op1.subevent == se1

    @classscope(attr='o')
    def test_add_with_seat_and_subevent_mismatch(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name="Foo", date_from=now())
        se2 = self.event.subevents.create(name="Bar", date_from=now())
        self.quota.subevent = se2
        self.quota.save()
        self.seat_a1.subevent = se1
        self.seat_a1.save()
        self.ocm.change_subevent(self.op1, se2)
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.ticket, None, price=Decimal('13.00'), subevent=se2, seat=self.seat_a1)

    @classscope(attr='o')
    def test_fee_change_value(self):
        fee = self.order.fees.create(fee_type="shipping", value=Decimal('5.00'))
        self.order.total += Decimal('5.00')
        self.order.save()
        self.ocm.change_fee(fee, Decimal('3.50'))
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('49.50')
        fee.refresh_from_db()
        assert fee.value == Decimal('3.50')

    @classscope(attr='o')
    def test_fee_change_value_tax_rate(self):
        fee = self.order.fees.create(fee_type="shipping", value=Decimal('5.00'), tax_rule=self.tr19)
        self.order.total += Decimal('5.00')
        self.order.save()
        self.ocm.change_fee(fee, Decimal('3.50'))
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('49.50')
        fee.refresh_from_db()
        assert fee.value == Decimal('3.50')
        assert fee.tax_rate == Decimal('19.00')
        assert fee.tax_value == Decimal('0.56')

    @classscope(attr='o')
    def test_fee_cancel(self):
        fee = self.order.fees.create(fee_type="shipping", value=Decimal('5.00'))
        self.order.total += Decimal('5.00')
        self.order.save()
        self.ocm.cancel_fee(fee)
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('46.00')
        fee.refresh_from_db()
        assert fee.canceled

    @classscope(attr='o')
    def test_clear_out_order(self):
        self.event.settings.ticket_secret_generator = "pretix_sig1"
        op = self.order.positions.first()
        s = op.secret
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.order.payments.create(amount=self.order.total, state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                                   provider='manual')
        cancel_order(self.order, cancellation_fee=Decimal('5.00'))
        self.order.refresh_from_db()
        assert self.order.total == Decimal('5.00')
        self.ocm.cancel_fee(self.order.fees.get())
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('0.00')
        assert self.order.status == Order.STATUS_CANCELED
        assert op.secret == s

    @classscope(attr='o')
    def test_clear_out_order_change_secrets(self):
        self.event.settings.ticket_secret_generator = "pretix_sig1"
        op = self.order.positions.first()
        s = op.secret
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self.order.payments.create(amount=self.order.total, state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                                   provider='manual')
        cancel_order(self.order, cancellation_fee=Decimal('5.00'))
        self.order.refresh_from_db()
        assert self.order.total == Decimal('5.00')
        self.ocm.cancel_fee(self.order.fees.get())
        self.ocm.commit()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('0.00')
        assert self.order.status == Order.STATUS_CANCELED
        op.refresh_from_db()
        assert op.secret != s

    @classscope(attr='o')
    def test_cancel_order_membership(self):
        mt = self.event.organizer.membership_types.create(name="foo")
        customer = self.event.organizer.customers.create()
        self.order.customer = customer
        m = customer.memberships.create(
            membership_type=mt,
            date_start=now(),
            date_end=now(),
            granted_in=self.order.positions.first(),
        )
        cancel_order(self.order)
        m.refresh_from_db()
        assert m.canceled

    @classscope(attr='o')
    def test_auto_change_payment_fee(self):
        fee2 = self.order.fees.create(fee_type=OrderFee.FEE_TYPE_SHIPPING, value=Decimal('0.50'))
        fee = self.order.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.46'))
        self.order.status = Order.STATUS_PAID
        self.order.total = Decimal('51.1')
        self.order.save()

        self.order.payments.create(state=OrderPayment.PAYMENT_STATE_PENDING, amount=Decimal('48.5'), fee=fee,
                                   provider="banktransfer")
        prov = self.ocm._get_payment_provider()
        prov.settings.set('_fee_percent', Decimal('10.00'))
        prov.settings.set('_fee_reverse_calc', False)

        self.ocm.cancel_fee(fee2)
        self.ocm.commit()
        assert self.order.total == Decimal('50.6')
        fee.refresh_from_db()
        assert fee.value == Decimal('4.6')

    @classscope(attr='o')
    def test_change_payment_fee(self):
        fee = self.order.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.46'))
        self.order.status = Order.STATUS_PAID
        self.order.total = Decimal('50.60')
        self.order.save()

        self.order.payments.create(state=OrderPayment.PAYMENT_STATE_PENDING, amount=Decimal('48.5'), fee=fee,
                                   provider="banktransfer")
        prov = self.ocm._get_payment_provider()
        prov.settings.set('_fee_percent', Decimal('10.00'))
        prov.settings.set('_fee_reverse_calc', False)

        self.ocm.change_fee(fee, Decimal('0.2'))
        self.ocm.commit()
        fee.refresh_from_db()
        assert fee.value == Decimal('0.20')
        self.order.refresh_from_db()
        assert self.order.total == Decimal('46.20')

    @classscope(attr='o')
    def test_cancel_payment_fee(self):
        fee = self.order.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.46'))
        self.order.status = Order.STATUS_PAID
        self.order.total = Decimal('50.60')
        self.order.save()

        self.order.payments.create(state=OrderPayment.PAYMENT_STATE_PENDING, amount=Decimal('48.5'), fee=fee,
                                   provider="banktransfer")
        prov = self.ocm._get_payment_provider()
        prov.settings.set('_fee_percent', Decimal('10.00'))
        prov.settings.set('_fee_reverse_calc', False)

        self.ocm.cancel_fee(fee)
        self.ocm.commit()
        fee.refresh_from_db()
        assert fee.canceled
        self.order.refresh_from_db()
        assert self.order.total == Decimal('46.00')

    @classscope(attr='o')
    def test_change_taxrate(self):
        self.ocm.change_tax_rule(self.op1, self.tr19)
        self.ocm.commit()
        self.order.refresh_from_db()
        nop = self.order.positions.first()
        assert nop.price == Decimal('23.00')
        assert nop.tax_rule != self.ticket.tax_rule
        assert nop.tax_rate == self.tr19.rate
        assert round_decimal(nop.price * (1 - 100 / (100 + self.tr19.rate))) == nop.tax_value

    @classscope(attr='o')
    def test_change_taxrate_and_product(self):
        self.ocm.change_item(self.op1, self.shirt, None)
        self.ocm.change_tax_rule(self.op1, self.tr7)
        self.ocm.commit()
        self.order.refresh_from_db()
        nop = self.order.positions.first()
        assert nop.item == self.shirt
        assert nop.price == Decimal('23.00')
        assert nop.tax_rule != self.shirt.tax_rule
        assert nop.tax_rate == self.tr7.rate
        assert round_decimal(nop.price * (1 - 100 / (100 + self.tr7.rate))) == nop.tax_value

    @classscope(attr='o')
    def test_change_taxrate_to_reverse_charge(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        InvoiceAddress.objects.create(
            order=self.order, is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )

        self.ocm.change_tax_rule(self.op1, self.tr19)
        self.ocm.commit()
        self.order.refresh_from_db()
        nop = self.order.positions.first()
        assert nop.price == Decimal('23.00')
        assert nop.tax_rule == self.tr19
        assert nop.tax_rate == Decimal('0.00')
        assert nop.tax_value == Decimal('0.00')

    @classscope(attr='o')
    def test_change_taxrate_to_country_specific(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.custom_rules = json.dumps([
            {'country': 'AT', 'address_type': '', 'action': 'vat', 'rate': '100.00'}
        ])
        self.tr19.save()
        InvoiceAddress.objects.create(
            order=self.order, is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )

        self.ocm.change_tax_rule(self.op1, self.tr19)
        self.ocm.commit()
        self.order.refresh_from_db()
        nop = self.order.positions.first()
        assert nop.price == Decimal('23.00')
        assert nop.tax_rule == self.tr19
        assert nop.tax_rate == Decimal('100.00')
        assert nop.tax_value == Decimal('11.50')

    @classscope(attr='o')
    def test_change_taxrate_from_reverse_charge(self):
        self.tr7.eu_reverse_charge = True
        self.tr7.home_country = Country('DE')
        self.tr7.save()
        nop = self.order.positions.first()
        nop.tax_value = Decimal('0.00')
        nop.tax_rate = Decimal('0.00')
        nop.save()
        InvoiceAddress.objects.create(
            order=self.order, is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )

        self.ocm.change_tax_rule(self.op1, self.tr19)
        self.ocm.commit()
        self.order.refresh_from_db()
        nop = self.order.positions.first()
        assert nop.price == Decimal('23.00')
        assert nop.tax_rule == self.tr19
        assert nop.tax_rate == Decimal('19.00')
        assert nop.tax_value == Decimal('3.67')

    @classscope(attr='o')
    def test_add_with_membership_required(self):
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.vip, None, price=Decimal('13.00'))
            self.ocm.commit()

    @classscope(attr='o')
    def test_add_with_membership_forbidden(self):
        self.order.customer = self.o.customers.create(email="foo@bar.com")
        m = self.order.customer.memberships.create(
            membership_type=self.mtype,
            date_start=self.event.date_from - timedelta(days=1),
            date_end=self.event.date_from + timedelta(days=1),
            attendee_name_parts={'_scheme': 'full', 'full_name': 'John Doe'},
        )
        with self.assertRaises(OrderError):
            self.ocm.add_position(self.ticket, None, price=Decimal('13.00'), membership=m)
            self.ocm.commit()

    @classscope(attr='o')
    def test_add_with_membership(self):
        self.order.customer = self.o.customers.create(email="foo@bar.com")
        m = self.order.customer.memberships.create(
            membership_type=self.mtype,
            date_start=self.event.date_from - timedelta(days=1),
            date_end=self.event.date_from + timedelta(days=1),
            attendee_name_parts={'_scheme': 'full', 'full_name': 'John Doe'},
        )
        self.ocm.add_position(self.vip, None, price=Decimal('13.00'), membership=m)
        self.ocm.commit()
        assert self.order.positions.last().used_membership == m

    @classscope(attr='o')
    def test_change_membership(self):
        self.order.customer = self.o.customers.create(email="foo@bar.com")
        m = self.order.customer.memberships.create(
            membership_type=self.mtype,
            date_start=self.event.date_from - timedelta(days=1),
            date_end=self.event.date_from + timedelta(days=1),
            attendee_name_parts={'_scheme': 'full', 'full_name': 'John Doe'},
        )
        m2 = self.order.customer.memberships.create(
            membership_type=self.mtype,
            date_start=self.event.date_from - timedelta(days=1),
            date_end=self.event.date_from + timedelta(days=1),
            attendee_name_parts={'_scheme': 'full', 'full_name': 'John Doe'},
        )
        self.op1.item = self.vip
        self.op1.used_membership = m
        self.op1.save()
        self.ocm.change_membership(self.op1, membership=m2)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.used_membership == m2

    @classscope(attr='o')
    def test_change_to_invalid_membership(self):
        self.order.customer = self.o.customers.create(email="foo@bar.com")
        m = self.order.customer.memberships.create(
            membership_type=self.mtype,
            date_start=self.event.date_from - timedelta(days=1),
            date_end=self.event.date_from + timedelta(days=1),
            attendee_name_parts={'_scheme': 'full', 'full_name': 'John Doe'},
        )
        m2 = self.order.customer.memberships.create(
            membership_type=self.mtype,
            date_start=self.event.date_from - timedelta(days=5),
            date_end=self.event.date_from - timedelta(days=1),
            attendee_name_parts={'_scheme': 'full', 'full_name': 'John Doe'},
        )
        self.op1.item = self.vip
        self.op1.used_membership = m
        self.op1.save()
        self.ocm.change_membership(self.op1, membership=m2)
        with self.assertRaises(OrderError):
            self.ocm.commit()

    @classscope(attr='o')
    def test_change_item_to_required_membership(self):
        self.order.customer = self.o.customers.create(email="foo@bar.com")
        self.ocm.change_item(self.op1, self.vip, None)
        with self.assertRaises(OrderError):
            self.ocm.commit()

    @classscope(attr='o')
    def test_change_membership_to_none(self):
        self.order.customer = self.o.customers.create(email="foo@bar.com")
        m = self.order.customer.memberships.create(
            membership_type=self.mtype,
            date_start=self.event.date_from - timedelta(days=1),
            date_end=self.event.date_from + timedelta(days=1),
            attendee_name_parts={'_scheme': 'full', 'full_name': 'John Doe'},
        )
        self.order.customer.memberships.create(
            membership_type=self.mtype,
            date_start=self.event.date_from - timedelta(days=1),
            date_end=self.event.date_from + timedelta(days=1),
            attendee_name_parts={'_scheme': 'full', 'full_name': 'John Doe'},
        )
        self.op1.item = self.vip
        self.op1.used_membership = m
        self.op1.save()
        self.ocm.change_item(self.op1, self.ticket, None)
        self.ocm.change_membership(self.op1, membership=None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.used_membership is None
        assert self.op1.item == self.ticket

    @classscope(attr='o')
    def test_add_block(self):
        self.ocm.add_block(self.op1, "admin")
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.blocked == ["admin"]
        bs = self.op1.blocked_secrets.get()
        assert bs.secret == self.op1.secret
        assert bs.blocked

    @classscope(attr='o')
    def test_remove_block(self):
        self.op1.blocked = ["admin"]
        self.op1.save()
        bs = self.op1.blocked_secrets.create(event=self.event, secret=self.op1.secret, blocked=True)
        self.ocm.remove_block(self.op1, "admin")
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.blocked is None
        bs.refresh_from_db()
        assert not bs.blocked

    @classscope(attr='o')
    def test_set_valid_from(self):
        old_secret = self.op1.secret
        dt = make_aware(datetime(2016, 9, 20, 15, 0, 0, 0))
        self.ocm.change_valid_from(self.op1, dt)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.valid_from == dt
        assert self.op1.secret == old_secret

    @classscope(attr='o')
    def test_set_valid_until(self):
        self.event.settings.ticket_secret_generator = "pretix_sig1"
        assign_ticket_secret(self.event, self.op1, force_invalidate=True, save=True)
        old_secret = self.op1.secret

        dt = make_aware(datetime(2022, 9, 20, 15, 0, 0, 0))
        self.ocm.change_valid_until(self.op1, dt)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.secret != old_secret

    @classscope(attr='o')
    def test_unset_valid_from_until(self):
        self.op1.valid_from = make_aware(datetime(2016, 9, 20, 15, 0, 0, 0))
        self.op1.valid_until = make_aware(datetime(2016, 9, 20, 15, 0, 0, 0))
        self.op1.save()
        self.ocm.change_valid_from(self.op1, None)
        self.ocm.change_valid_until(self.op1, None)
        self.ocm.commit()
        self.op1.refresh_from_db()
        assert self.op1.valid_from is None
        assert self.op1.valid_until is None


@pytest.mark.django_db
def test_autocheckin(clist_autocheckin, event):
    today = now()
    tr7 = event.tax_rules.create(rate=Decimal('17.00'))
    ticket = Item.objects.create(event=event, name='Early-bird ticket', tax_rule=tr7,
                                 default_price=Decimal('23.00'), admission=True)
    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123"
    )
    order = _create_order(event, email='dummy@example.org', positions=[cp1],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de')[0]
    assert "web" in clist_autocheckin.auto_checkin_sales_channels
    assert order.positions.first().checkins.first().auto_checked_in

    clist_autocheckin.auto_checkin_sales_channels = []
    clist_autocheckin.save()

    order = _create_order(event, email='dummy@example.org', positions=[cp1],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de')[0]
    assert clist_autocheckin.auto_checkin_sales_channels == []
    assert order.positions.first().checkins.count() == 0


@pytest.mark.django_db
def test_saleschannel_testmode_restriction(event):
    today = now()
    tr7 = event.tax_rules.create(rate=Decimal('17.00'))
    ticket = Item.objects.create(event=event, name='Early-bird ticket', tax_rule=tr7,
                                 default_price=Decimal('23.00'), admission=True)
    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123"
    )

    order = _create_order(event, email='dummy@example.org', positions=[cp1],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de', sales_channel='web')[0]
    assert not order.testmode

    order = _create_order(event, email='dummy@example.org', positions=[cp1],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de', sales_channel=FoobazSalesChannel.identifier)[0]
    assert not order.testmode

    event.testmode = True
    order = _create_order(event, email='dummy@example.org', positions=[cp1],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de', sales_channel='web')[0]
    assert order.testmode

    order = _create_order(event, email='dummy@example.org', positions=[cp1],
                          now_dt=today,
                          payment_requests=[{
                              "id": "test0",
                              "provider": "free",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": FreeOrderProvider(event),
                          }],
                          locale='de', sales_channel=FoobazSalesChannel.identifier)[0]
    assert not order.testmode


@pytest.mark.django_db
def test_giftcard_multiple(event):
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 default_price=Decimal('23.00'), admission=True)
    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123"
    )
    gc1 = event.organizer.issued_gift_cards.create(currency="EUR")
    gc1.transactions.create(value=12, acceptor=event.organizer)
    gc2 = event.organizer.issued_gift_cards.create(currency="EUR")
    gc2.transactions.create(value=12, acceptor=event.organizer)
    order = _create_order(
        event, email='dummy@example.org', positions=[cp1],
        now_dt=now(),
        payment_requests=[
            {
                "id": "test0",
                "provider": "giftcard",
                "max_value": "12.00",
                "min_value": None,
                "multi_use_supported": True,
                "info_data": {
                    "gift_card": gc1.pk
                },
                "pprov": GiftCardPayment(event),
            },
            {
                "id": "test1",
                "provider": "giftcard",
                "max_value": "12.00",
                "min_value": None,
                "multi_use_supported": True,
                "info_data": {
                    "gift_card": gc2.pk
                },
                "pprov": GiftCardPayment(event),
            },
        ],
        locale='de'
    )[0]
    assert order.payments.count() == 2
    for p in order.payments.all():
        p.payment_provider.execute_payment(None, p)

    assert order.payments.get(info__icontains=gc1.pk).amount == Decimal('12.00')
    assert order.payments.get(info__icontains=gc2.pk).amount == Decimal('11.00')
    gc1 = GiftCard.objects.get(pk=gc1.pk)
    assert gc1.value == 0
    gc2 = GiftCard.objects.get(pk=gc2.pk)
    assert gc2.value == 1


@pytest.mark.django_db
def test_giftcard_partial(event):
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 default_price=Decimal('23.00'), admission=True)
    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123"
    )
    gc1 = event.organizer.issued_gift_cards.create(currency="EUR")
    gc1.transactions.create(value=12, acceptor=event.organizer)
    order = _create_order(
        event, email='dummy@example.org', positions=[cp1],
        now_dt=now(),
        payment_requests=[
            {
                "id": "test0",
                "provider": "giftcard",
                "max_value": "12.00",
                "min_value": None,
                "multi_use_supported": True,
                "info_data": {
                    "gift_card": gc1.pk
                },
                "pprov": GiftCardPayment(event),
            },
            {
                "id": "test1",
                "provider": "banktransfer",
                "max_value": None,
                "min_value": None,
                "multi_use_supported": False,
                "info_data": {},
                "pprov": BankTransfer(event),
            },
        ],
        locale='de'
    )[0]
    assert order.payments.count() == 2
    for p in order.payments.all():
        p.payment_provider.execute_payment(None, p)
    assert order.payments.get(info__icontains=gc1.pk).amount == Decimal('12.00')
    assert order.payments.get(provider='banktransfer').amount == Decimal('11.00')
    gc1 = GiftCard.objects.get(pk=gc1.pk)
    assert gc1.value == 0


@pytest.mark.django_db
def test_giftcard_payment_fee(event):
    event.settings.set('payment_banktransfer__fee_percent', Decimal('10.00'))
    event.settings.set('payment_banktransfer__fee_reverse_calc', False)
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 default_price=Decimal('23.00'), admission=True)
    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123"
    )
    gc1 = event.organizer.issued_gift_cards.create(currency="EUR")
    gc1.transactions.create(value=12, acceptor=event.organizer)
    order = _create_order(
        event, email='dummy@example.org', positions=[cp1],
        now_dt=now(),
        payment_requests=[
            {
                "id": "test0",
                "provider": "giftcard",
                "max_value": "12.00",
                "min_value": None,
                "multi_use_supported": True,
                "info_data": {
                    "gift_card": gc1.pk
                },
                "pprov": GiftCardPayment(event),
            },
            {
                "id": "test1",
                "provider": "banktransfer",
                "max_value": None,
                "min_value": None,
                "multi_use_supported": False,
                "info_data": {},
                "pprov": BankTransfer(event),
            },
        ],
        locale='de'
    )[0]
    assert order.payments.count() == 2
    assert order.payments.get(info__icontains=gc1.pk).amount == Decimal('12.00')
    assert order.payments.get(provider='banktransfer').amount == Decimal('12.10')
    for p in order.payments.all():
        p.payment_provider.execute_payment(None, p)
    assert order.fees.get().value == Decimal('1.10')
    gc1 = GiftCard.objects.get(pk=gc1.pk)
    assert gc1.value == 0


@pytest.mark.django_db
def test_giftcard_invalid_currency(event):
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 default_price=Decimal('23.00'), admission=True)
    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123"
    )
    gc1 = event.organizer.issued_gift_cards.create(currency="USD")
    gc1.transactions.create(value=12, acceptor=event.organizer)
    _create_order(
        event, email='dummy@example.org', positions=[cp1],
        now_dt=now(),
        payment_requests=[
            {
                "id": "test0",
                "provider": "giftcard",
                "max_value": "12.00",
                "min_value": None,
                "multi_use_supported": True,
                "info_data": {
                    "gift_card": gc1.pk
                },
                "pprov": GiftCardPayment(event),
            },
            {
                "id": "test1",
                "provider": "banktransfer",
                "max_value": None,
                "min_value": None,
                "multi_use_supported": False,
                "info_data": {},
                "pprov": BankTransfer(event),
            },
        ],
        locale='de'
    )[0]
    with pytest.raises(PaymentException):
        for p in Order.objects.get().payments.all():
            p.payment_provider.execute_payment(None, p)


@pytest.mark.django_db
def test_giftcard_invalid_organizer(event):
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 default_price=Decimal('23.00'), admission=True)
    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123"
    )
    o2 = Organizer.objects.create(slug="foo", name="bar")
    gc1 = o2.issued_gift_cards.create(currency="EUR")
    gc1.transactions.create(value=12, acceptor=event.organizer)
    _create_order(
        event, email='dummy@example.org', positions=[cp1],
        now_dt=now(),
        payment_requests=[
            {
                "id": "test0",
                "provider": "giftcard",
                "max_value": "12.00",
                "min_value": None,
                "multi_use_supported": True,
                "info_data": {
                    "gift_card": gc1.pk
                },
                "pprov": GiftCardPayment(event),
            },
            {
                "id": "test1",
                "provider": "banktransfer",
                "max_value": None,
                "min_value": None,
                "multi_use_supported": False,
                "info_data": {},
                "pprov": BankTransfer(event),
            },
        ],
        locale='de'
    )[0]
    with pytest.raises(PaymentException):
        for p in Order.objects.get().payments.all():
            p.payment_provider.execute_payment(None, p)


@pytest.mark.django_db
def test_giftcard_test_mode_invalid(event):
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 default_price=Decimal('23.00'), admission=True)
    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123"
    )
    gc1 = event.organizer.issued_gift_cards.create(currency="EUR", testmode=True)
    gc1.transactions.create(value=12, acceptor=event.organizer)
    _create_order(
        event, email='dummy@example.org', positions=[cp1],
        now_dt=now(),
        payment_requests=[
            {
                "id": "test0",
                "provider": "giftcard",
                "max_value": "12.00",
                "min_value": None,
                "multi_use_supported": True,
                "info_data": {
                    "gift_card": gc1.pk
                },
                "pprov": GiftCardPayment(event),
            },
            {
                "id": "test1",
                "provider": "banktransfer",
                "max_value": None,
                "min_value": None,
                "multi_use_supported": False,
                "info_data": {},
                "pprov": BankTransfer(event),
            },
        ],
        locale='de'
    )[0]
    with pytest.raises(PaymentException):
        for p in Order.objects.get().payments.all():
            p.payment_provider.execute_payment(None, p)


@pytest.mark.django_db
def test_giftcard_test_mode_event(event):
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 default_price=Decimal('23.00'), admission=True)
    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123"
    )
    event.testmode = True
    event.save()
    gc1 = event.organizer.issued_gift_cards.create(currency="EUR", testmode=False)
    gc1.transactions.create(value=12, acceptor=event.organizer)
    _create_order(
        event, email='dummy@example.org', positions=[cp1],
        now_dt=now(),
        payment_requests=[
            {
                "id": "test0",
                "provider": "giftcard",
                "max_value": "12.00",
                "min_value": None,
                "multi_use_supported": True,
                "info_data": {
                    "gift_card": gc1.pk
                },
                "pprov": GiftCardPayment(event),
            },
            {
                "id": "test1",
                "provider": "banktransfer",
                "max_value": None,
                "min_value": None,
                "multi_use_supported": False,
                "info_data": {},
                "pprov": BankTransfer(event),
            },
        ],
        locale='de'
    )[0]
    with pytest.raises(PaymentException):
        for p in Order.objects.get().payments.all():
            p.payment_provider.execute_payment(None, p)


@pytest.mark.django_db
def test_giftcard_swap(event):
    ticket = Item.objects.create(event=event, name='Early-bird ticket', issue_giftcard=True,
                                 default_price=Decimal('23.00'), admission=True)
    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123"
    )
    gc1 = event.organizer.issued_gift_cards.create(currency="EUR", testmode=False)
    gc1.transactions.create(value=12, acceptor=event.organizer)
    _create_order(
        event, email='dummy@example.org', positions=[cp1],
        now_dt=now(),
        payment_requests=[
            {
                "id": "test0",
                "provider": "giftcard",
                "max_value": "12.00",
                "min_value": None,
                "multi_use_supported": True,
                "info_data": {
                    "gift_card": gc1.pk
                },
                "pprov": GiftCardPayment(event),
            },
            {
                "id": "test1",
                "provider": "banktransfer",
                "max_value": None,
                "min_value": None,
                "multi_use_supported": False,
                "info_data": {},
                "pprov": BankTransfer(event),
            },
        ],
        locale='de'
    )[0]
    with pytest.raises(PaymentException):
        for p in Order.objects.get().payments.all():
            p.payment_provider.execute_payment(None, p)


@pytest.mark.django_db
def test_issue_when_paid_and_changed(event):
    ticket = Item.objects.create(event=event, name='Early-bird ticket', issue_giftcard=True,
                                 default_price=Decimal('23.00'), admission=True)
    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123"
    )
    q = event.quotas.create(size=None, name="foo")
    q.items.add(ticket)
    order = _create_order(
        event, email='dummy@example.org', positions=[cp1],
        now_dt=now(),
        payment_requests=[
            {
                "id": "test1",
                "provider": "banktransfer",
                "max_value": None,
                "min_value": None,
                "multi_use_supported": False,
                "info_data": {},
                "pprov": BankTransfer(event),
            },
        ],
        locale='de'
    )[0]
    op = order.positions.first()
    assert not op.issued_gift_cards.exists()
    order.payments.first().confirm()
    gc1 = op.issued_gift_cards.get()
    assert gc1.value == op.price
    op.refresh_from_db()
    assert op.secret == gc1.secret

    ocm = OrderChangeManager(order)
    ocm.add_position(ticket, None, Decimal('12.00'))
    ocm.commit()
    order.payments.create(
        provider='manual', amount=order.pending_sum
    ).confirm()

    assert op.issued_gift_cards.count() == 1
    op2 = order.positions.last()
    gc2 = op2.issued_gift_cards.get()
    assert gc2.value == op2.price


class OrderReactivateTest(TestCase):
    def setUp(self):
        super().setUp()
        self.o = Organizer.objects.create(name='Dummy', slug='dummy')
        with scope(organizer=self.o):
            self.event = Event.objects.create(organizer=self.o, name='Dummy', slug='dummy', date_from=now(),
                                              plugins='tests.testdummy')
            self.order = Order.objects.create(
                code='FOO', event=self.event, email='dummy@dummy.test',
                status=Order.STATUS_CANCELED, locale='en',
                datetime=now(), expires=now() + timedelta(days=1),
                cancellation_date=now(),
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
            self.stalls = Item.objects.create(event=self.event, name='Stalls',
                                              default_price=Decimal('23.00'), admission=True)
            self.plan = SeatingPlan.objects.create(
                name="Plan", organizer=self.o, layout="{}"
            )
            self.event.seat_category_mappings.create(
                layout_category='Stalls', product=self.stalls
            )
            self.quota = self.event.quotas.create(name='Test', size=None)
            self.quota.items.add(self.stalls)
            self.quota.items.add(self.ticket)
            self.seat_a1 = self.event.seats.create(seat_number="A1", product=self.stalls, seat_guid="A1")
            generate_invoice(self.order)
            self.order.create_transactions()
            djmail.outbox = []

    @classscope(attr='o')
    def test_paid(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        with pytest.raises(OrderError):
            reactivate_order(self.order)

    @classscope(attr='o')
    def test_reactivate_unpaid(self):
        e = self.order.expires
        reactivate_order(self.order)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PENDING
        assert self.order.all_logentries().last().action_type == 'pretix.event.order.reactivated'
        assert self.order.invoices.count() == 3
        assert self.order.expires > e > now()

    @classscope(attr='o')
    def test_reactivate_paid(self):
        assert self.order.transactions.aggregate(s=Sum(F('price') * F('count')))['s'] in (None, Decimal('0.00'))
        self.order.payments.create(state=OrderPayment.PAYMENT_STATE_CONFIRMED, amount=48.5)
        reactivate_order(self.order)
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PAID
        assert self.order.all_logentries().last().action_type == 'pretix.event.order.reactivated'
        assert self.order.invoices.count() == 3
        assert not self.order.cancellation_date
        assert self.order.transactions.aggregate(s=Sum(F('price') * F('count')))['s'] == Decimal('46.00')

    @classscope(attr='o')
    def test_reactivate_sold_out(self):
        self.quota.size = 0
        self.quota.save()
        with pytest.raises(OrderError):
            reactivate_order(self.order)

    @classscope(attr='o')
    def test_reactivate_seat_taken(self):
        self.op1.item = self.stalls
        self.op1.seat = self.seat_a1
        self.op1.save()
        self.seat_a1.blocked = True
        self.seat_a1.save()
        with pytest.raises(OrderError):
            reactivate_order(self.order)

    @classscope(attr='o')
    def test_reactivate_voucher_ok(self):
        self.op1.voucher = self.event.vouchers.create(code="FOO", item=self.ticket, redeemed=0, max_usages=1)
        self.op1.save()
        reactivate_order(self.order)
        v = self.op1.voucher
        v.refresh_from_db()
        assert v.redeemed == 1

    @classscope(attr='o')
    def test_reactivate_voucher_budget(self):
        self.op1.voucher = self.event.vouchers.create(code="FOO", item=self.ticket, budget=Decimal('0.00'))
        self.op1.voucher_budget_use = self.op1.price
        self.op1.save()
        with pytest.raises(OrderError):
            reactivate_order(self.order)

    @classscope(attr='o')
    def test_reactivate_voucher_used(self):
        self.op1.voucher = self.event.vouchers.create(code="FOO", item=self.ticket, redeemed=1, max_usages=1)
        self.op1.save()
        with pytest.raises(OrderError):
            reactivate_order(self.order)
        v = self.op1.voucher
        v.refresh_from_db()
        assert v.redeemed == 1

    @classscope(attr='o')
    def test_reactivate_gift_card(self):
        gc = self.o.issued_gift_cards.create(currency="EUR", issued_in=self.op1)
        reactivate_order(self.order)
        assert gc.value == 23

    @classscope(attr='o')
    def test_reactivate_membership(self):
        mt = self.event.organizer.membership_types.create(name="foo")
        customer = self.event.organizer.customers.create()
        self.order.customer = customer
        self.order.save()
        m = customer.memberships.create(
            membership_type=mt,
            date_start=now(),
            date_end=now(),
            granted_in=self.order.positions.first(),
            canceled=True,
        )
        reactivate_order(self.order)
        m.refresh_from_db()
        assert not m.canceled


@pytest.mark.django_db
def test_autocreate_medium(event):
    ticket = Item.objects.create(event=event, name='Early-bird ticket', issue_giftcard=True,
                                 default_price=Decimal('23.00'), admission=True, media_type='barcode',
                                 media_policy=Item.MEDIA_POLICY_REUSE_OR_NEW)
    cp1 = CartPosition.objects.create(
        item=ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123"
    )
    q = event.quotas.create(size=None, name="foo")
    q.items.add(ticket)
    order = _create_order(
        event, email='dummy@example.org', positions=[cp1],
        now_dt=now(),
        payment_requests=[
            {
                "id": "test1",
                "provider": "banktransfer",
                "max_value": None,
                "min_value": None,
                "multi_use_supported": False,
                "info_data": {},
                "pprov": BankTransfer(event),
            },
        ],
        locale='de'
    )[0]
    op = order.positions.first()
    m = op.linked_media.get()
    assert m.type == "barcode"
