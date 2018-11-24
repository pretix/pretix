from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.utils.timezone import now
from PyPDF2 import PdfFileReader

from pretix.base.models import (
    Event, Item, ItemVariation, Order, OrderPosition, Organizer,
)
from pretix.plugins.ticketoutputpdf.ticketoutput import PdfTicketOutput


@pytest.fixture
def env0():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), live=True
    )
    o1 = Order.objects.create(
        code='FOOBAR', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=Decimal('13.37'),
    )
    shirt = Item.objects.create(event=event, name='T-Shirt', default_price=12)
    shirt_red = ItemVariation.objects.create(item=shirt, default_price=14, value="Red")
    OrderPosition.objects.create(
        order=o1, item=shirt, variation=shirt_red,
        price=12, attendee_name_parts={}, secret='1234'
    )
    OrderPosition.objects.create(
        order=o1, item=shirt, variation=shirt_red,
        price=12, attendee_name_parts={}, secret='5678'
    )
    return event, o1


@pytest.mark.django_db
def test_generate_pdf(env0):
    event, order = env0
    event.settings.set('ticketoutput_pdf_code_x', 30)
    event.settings.set('ticketoutput_pdf_code_y', 50)
    event.settings.set('ticketoutput_pdf_code_s', 2)
    o = PdfTicketOutput(event)
    fname, ftype, buf = o.generate(order.positions.first())
    assert ftype == 'application/pdf'
    pdf = PdfFileReader(BytesIO(buf))
    assert pdf.numPages == 1
