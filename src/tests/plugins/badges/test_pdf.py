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


@pytest.mark.django_db
def test_generate_pdf_multi(env):
    event, order, shirt = env
    event.badge_layouts.create(name="Default", default=True)
    e = BadgeExporter(event)
    fname, ftype, buf = e.render({
        'items': [shirt.pk],
        'rendering': 'a4_a6l',
        'include_pending': True
    })
    assert ftype == 'application/pdf'
    pdf = PdfFileReader(BytesIO(buf))
    assert pdf.numPages == 1
