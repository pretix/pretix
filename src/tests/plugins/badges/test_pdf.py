from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.utils.timezone import now
from django_scopes import scope
from PyPDF2 import PdfFileReader

from pretix.base.models import (
    Event, Item, ItemVariation, Order, OrderPosition, Organizer,
)
from pretix.base.services.orders import OrderError
from pretix.plugins.badges.exporters import BadgeExporter


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    with scope(organizer=o):
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
        yield event, o1, shirt


@pytest.mark.django_db
def test_generate_pdf(env):
    event, order, shirt = env
    event.badge_layouts.create(name="Default", default=True)
    e = BadgeExporter(event)
    with pytest.raises(OrderError):
        e.render({
            'items': [shirt.pk],
            'rendering': 'one',
            'include_pending': False
        })

    with pytest.raises(OrderError):
        e.render({
            'items': [],
            'rendering': 'one',
            'include_pending': True
        })

    fname, ftype, buf = e.render({
        'items': [shirt.pk],
        'rendering': 'one',
        'include_pending': True
    })
    assert ftype == 'application/pdf'
    pdf = PdfFileReader(BytesIO(buf))
    assert pdf.numPages == 2
