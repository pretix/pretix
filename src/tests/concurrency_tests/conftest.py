#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
from datetime import datetime, timedelta

import aiohttp
import pytest
import pytest_asyncio
from django.utils.timezone import now
from django_scopes import scopes_disabled
from pytz import UTC

from pretix.base.models import (
    Device, Event, Item, Organizer, Quota, SeatingPlan,
)
from pretix.base.models.devices import generate_api_token


@pytest.fixture(autouse=True)
def autoskip(request, settings):
    if 'sqlite3' in settings.DATABASES['default']['ENGINE']:
        pytest.skip("cannot be run on sqlite")
    if not request.config.getvalue("reuse_db"):
        pytest.skip("only works with --reuse-db due to some weird connection handling bug")


@pytest.fixture
@scopes_disabled()
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy', plugins='pretix.plugins.banktransfer')


@pytest.fixture
@scopes_disabled()
def event(organizer):
    e = Event.objects.create(
        organizer=organizer, name='Dummy', slug='dummy',
        date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC),
        presale_end=now() + timedelta(days=300),
        plugins='pretix.plugins.banktransfer,pretix.plugins.ticketoutputpdf',
        is_public=True, live=True
    )
    e.item_meta_properties.create(name="day", default="Monday")
    e.settings.timezone = 'Europe/Berlin'
    e.settings.payment_banktransfer__enabled = True
    return e


@pytest.fixture
@scopes_disabled()
def item(event):
    return Item.objects.create(
        event=event,
        name='Regular ticket',
        default_price=0,
    )


@pytest.fixture
@scopes_disabled()
def quota(event, item):
    q = Quota.objects.create(
        event=event,
        size=10,
        name='Regular tickets'
    )
    q.items.add(item)
    return q


@pytest.fixture
@scopes_disabled()
def voucher(event, item):
    return event.vouchers.create(code="Foo", max_usages=1)


@pytest.fixture
@scopes_disabled()
def membership_type(event):
    return event.organizer.membership_types.create(name="foo", allow_parallel_usage=False)


@pytest.fixture
@scopes_disabled()
def customer(event, membership_type):
    return event.organizer.customers.create(email="admin@localhost", is_active=True, is_verified=True)


@pytest.fixture
@scopes_disabled()
def membership(event, membership_type, customer):
    return customer.memberships.create(
        membership_type=membership_type,
        date_start=datetime(2017, 1, 1, 0, 0, tzinfo=UTC),
        date_end=datetime(2099, 1, 1, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
@scopes_disabled()
def seat(event, organizer, item):
    SeatingPlan.objects.create(
        name="Plan", organizer=organizer, layout="{}"
    )
    event.seat_category_mappings.create(
        layout_category='Stalls', product=item
    )
    return event.seats.create(seat_number="A1", product=item, seat_guid="A1")


@pytest.fixture
@scopes_disabled()
def device(organizer):
    return Device.objects.create(
        organizer=organizer,
        all_events=True,
        name='Foo',
        initialized=now(),
        api_token=generate_api_token()
    )


@pytest_asyncio.fixture
async def session(live_server, event):
    async with aiohttp.ClientSession() as session:
        yield session
