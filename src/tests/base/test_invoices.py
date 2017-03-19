from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now

from pretix.base.models import (
    Event, Invoice, InvoiceAddress, Item, ItemVariation, Order, OrderPosition,
    Organizer,
)
from pretix.base.services.invoices import (
    build_preview_invoice_pdf, generate_cancellation, generate_invoice,
    invoice_pdf_task, regenerate_invoice,
)


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    o = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0, payment_provider='banktransfer',
        payment_fee=Decimal('0.25'), payment_fee_tax_rate=0,
        payment_fee_tax_value=0, locale='en'
    )
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 category=None, default_price=23,
                                 admission=True)
    t_shirt = Item.objects.create(event=event, name='T-Shirt',
                                  category=None, default_price=42,
                                  admission=True)
    variation = ItemVariation.objects.create(value='M', item=t_shirt)
    OrderPosition.objects.create(
        order=o,
        item=ticket,
        variation=None,
        price=Decimal("23.00"),
        positionid=1,
    )
    OrderPosition.objects.create(
        order=o,
        item=t_shirt,
        variation=variation,
        price=Decimal("42.00"),
        positionid=2,
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
    assert inv.lines.count() == 3
    first = inv.lines.first()
    assert 'Early-bird' in first.description
    assert first.gross_value == Decimal('23.00')

    second = inv.lines.all()[1]
    assert 'T-Shirt' in second.description
    assert 'M' in second.description
    assert second.gross_value == Decimal('42.00')

    last = inv.lines.last()
    assert 'Payment' in last.description
    assert last.gross_value == order.payment_fee
    assert last.tax_rate == order.payment_fee_tax_rate
    assert last.tax_value == order.payment_fee_tax_value
    assert inv.invoice_to == ""


@pytest.mark.django_db
def test_rebuilding(env):
    event, order = env
    inv = generate_invoice(order)
    inv2 = regenerate_invoice(inv)
    assert inv.order == inv2.order

    inv3 = generate_cancellation(inv)
    inv4 = regenerate_invoice(inv3)
    assert inv3.order == inv4.order


@pytest.mark.django_db
def test_cannot_delete_invoice(env):
    event, order = env
    inv = generate_invoice(order)
    with pytest.raises(Exception):
        inv.delete()


@pytest.mark.django_db
def test_cannot_write_invoice_without_order(env):
    event, _ = env
    with pytest.raises(Exception):
        i = Invoice(order=None, event=event)
        i.save()


@pytest.mark.django_db
def test_pdf_generation(env):
    event, order = env
    inv = generate_invoice(order)
    cancellation = generate_cancellation(inv)
    assert invoice_pdf_task(inv.pk)
    assert invoice_pdf_task(cancellation.pk)


@pytest.mark.django_db
def test_pdf_generation_custom_text(env):
    event, order = env
    event.settings.set('invoice_introductory_text', 'introductory invoice text')
    # set a really long additional text, to make the invoice span two pages
    event.settings.set('invoice_additional_text', 'additional invoice text\n' * 100)
    event.settings.set('show_date_to', False)
    inv = generate_invoice(order)
    assert invoice_pdf_task(inv.pk)


@pytest.mark.django_db
def test_pdf_preview_generation(env):
    event, order = env
    assert build_preview_invoice_pdf(event)


@pytest.mark.django_db
def test_invoice_numbers(env):
    event, order = env
    order2 = Order.objects.create(
        code='BAR', event=event, email='dummy2@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0, payment_provider='banktransfer',
        payment_fee=Decimal('0.25'), payment_fee_tax_rate=0,
        payment_fee_tax_value=0, locale='en'
    )
    inv1 = generate_invoice(order)
    inv2 = generate_invoice(order)

    event.settings.set('invoice_numbers_consecutive', False)
    inv3 = generate_invoice(order)
    inv4 = generate_invoice(order)
    inv21 = generate_invoice(order2)
    inv22 = generate_invoice(order2)

    event.settings.set('invoice_numbers_consecutive', True)
    inv5 = generate_invoice(order)
    inv23 = generate_invoice(order2)

    # expected behaviour for switching between numbering formats
    assert inv1.invoice_no == '00001'
    assert inv2.invoice_no == '00002'
    assert inv3.invoice_no == '{}-3'.format(order.code)
    assert inv4.invoice_no == '{}-4'.format(order.code)
    assert inv5.invoice_no == '00003'

    # test that separate orders are counted separately in this mode
    assert inv21.invoice_no == '{}-1'.format(order2.code)
    assert inv22.invoice_no == '{}-2'.format(order2.code)
    # but consecutively in this mode
    assert inv23.invoice_no == '00004'

    # test Invoice.number, too
    assert inv1.number == '{}-00001'.format(event.slug.upper())
    assert inv3.number == '{}-{}-3'.format(event.slug.upper(), order.code)
