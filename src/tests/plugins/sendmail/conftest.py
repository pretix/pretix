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
import datetime

import pytest
from django.utils.timezone import now

from pretix.base.models import Event, Item, Order, OrderPosition, Organizer


@pytest.fixture
def event():
    """Returns an event instance"""
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), live=True,
        plugins='pretix.plugins.sendmail,tests.testdummy',
    )
    return event


@pytest.fixture
def item(event):
    """Returns an item instance"""
    return Item.objects.create(name='Test item', event=event, default_price=13)


@pytest.fixture
def item2(event):
    return Item.objects.create(name='Test item 2', event=event, default_price=11)


@pytest.fixture
def checkin_list(event):
    """Returns an checkin list instance"""
    return event.checkin_lists.create(name="Test Checkinlist", all_products=True)


@pytest.fixture
def order(item):
    """Returns an order instance"""
    o = Order.objects.create(event=item.event, status=Order.STATUS_PENDING,
                             expires=now() + datetime.timedelta(hours=1),
                             total=13, code='DUMMY', email='dummy@dummy.test',
                             datetime=now(), locale='en')
    return o


@pytest.fixture
def pos(order, item):
    return OrderPosition.objects.create(order=order, item=item, price=13)


@pytest.fixture
def event_series(event):
    event.has_subevents = True
    event.save()
    return event


@pytest.fixture
def subevent1(event_series):
    se1 = event_series.subevents.create(name='Meow', date_from=now() + datetime.timedelta(days=1))
    return se1


@pytest.fixture
def subevent2(event_series):
    se2 = event_series.subevents.create(name='Foo', date_from=now() + datetime.timedelta(days=3))
    return se2
