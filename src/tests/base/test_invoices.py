from datetime import timedelta

import pytest
from django.utils.timezone import now
from decimal import Decimal

from pretix.base.models import Event, Organizer, Order, Item, OrderPosition, InvoiceAddress
from pretix.base.payment import FreeOrderProvider
from pretix.base.services.invoices import generate_invoice


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='banktransfer'
    )
    o = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0, payment_provider='banktransfer',
        payment_fee=Decimal('0.25'), payment_fee_tax_rate=0,
        payment_fee_tax_value=0
    )
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 category=None, default_price=23,
                                 admission=True)
    OrderPosition.objects.create(
        order=o,
        item=ticket,
        variation=None,
        price=Decimal("14"),
    )
    return event, o


@pytest.mark.django_db
def test_locale_setting(env):
    event, order = env
    event.settings.set('invoice_language', 'de')
    inv = generate_invoice(order)
    assert inv.locale == 'de'


@pytest.mark.django_db
def test_locale_user(env):
    event, order = env
    order.locale = 'en'
    event.settings.set('invoice_language', '__user__')
    inv = generate_invoice(order)
    assert inv.locale == order.locale


@pytest.mark.django_db
def test_address(env):
    event, order = env
    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street',
                                  zipcode='12345', city='London', country='UK',
                                  order=order)
    inv = generate_invoice(order)
    assert inv.invoice_to == "Acme Company\n\n221B Baker Street\n12345 London\nUK"


@pytest.mark.django_db
def test_address_vat_id(env):
    event, order = env
    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street',
                                  name='Sherlock Holmes', zipcode='12345', city='London', country='UK',
                                  vat_id='UK1234567', order=order)
    inv = generate_invoice(order)
    assert inv.invoice_to == "Acme Company\nSherlock Holmes\n221B Baker Street\n12345 London\nUK\nVAT-ID: UK1234567"


@pytest.mark.django_db
def test_positions(env):
    event, order = env
    inv = generate_invoice(order)
    assert inv.lines.count() == 2
    first = inv.lines.first()
    assert 'Early-bird' in first.description
    assert first.gross_value == Decimal('23.00')

    last = inv.lines.last()
    assert 'Payment' in last.description
    assert last.gross_value == order.payment_fee
    assert last.tax_rate == order.payment_fee_tax_rate
    assert last.tax_value == order.payment_fee_tax_value
    assert inv.invoice_to == "Acme Company\n\n221B Baker Street\n12345 London\nUK"
