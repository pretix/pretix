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
import asyncio

import pytest
from asgiref.sync import sync_to_async
from django_scopes import scopes_disabled

from pretix.base.models import Order, OrderPosition


async def post_code(session, url, data, **kwargs):
    async with session.post(url, json=data, **kwargs) as response:
        return response.status


@pytest.mark.asyncio
async def test_quota_race_condition_same_order_code(live_server, session, device, event, item, quota):
    url = f"/api/v1/organizers/{event.organizer.slug}/events/{event.slug}/orders/?_debug_flag=sleep-after-quota-check"
    payload = {
        "code": "ABC12",
        "email": "dummy@dummy.test",
        "phone": "+49622112345",
        "locale": "en",
        "sales_channel": "web",
        "valid_if_pending": True,
        "fees": [],
        "payment_provider": "banktransfer",
        "positions": [
            {
                "positionid": 1,
                "item": item.pk,
                "variation": None,
                "price": "23.00",
                "attendee_name_parts": {"full_name": "Peter"},
                "attendee_email": None,
                "addon_to": None,
                "company": "FOOCORP",
                "answers": [],
                "subevent": None
            }
        ],
    }

    r1, r2 = await asyncio.gather(
        post_code(session, f"{live_server}{url}", data=payload,
                  headers={"Authorization": f"Device {device.api_token}"}),
        post_code(session, f"{live_server}{url}", data=payload,
                  headers={"Authorization": f"Device {device.api_token}"}),
    )
    with scopes_disabled():
        assert await sync_to_async(Order.objects.filter(code="ABC12").count)() == 1
    assert [r1, r2].count(201) == 1
    assert [r1, r2].count(400) == 1


@pytest.mark.asyncio
async def test_quota_race_condition_same_ticket_secret(live_server, session, device, event, item, quota):
    url = f"/api/v1/organizers/{event.organizer.slug}/events/{event.slug}/orders/?_debug_flag=sleep-after-quota-check"
    payload = {
        "email": "dummy@dummy.test",
        "phone": "+49622112345",
        "locale": "en",
        "sales_channel": "web",
        "valid_if_pending": True,
        "fees": [],
        "payment_provider": "banktransfer",
        "positions": [
            {
                "positionid": 1,
                "item": item.pk,
                "variation": None,
                "price": "23.00",
                "attendee_name_parts": {"full_name": "Peter"},
                "attendee_email": None,
                "addon_to": None,
                "company": "FOOCORP",
                "answers": [],
                "secret": "foobarbaz",
                "subevent": None
            }
        ],
    }

    # Other one is just assigned differently
    r1, r2 = await asyncio.gather(
        post_code(session, f"{live_server}{url}", data=payload,
                  headers={"Authorization": f"Device {device.api_token}"}),
        post_code(session, f"{live_server}{url}", data=payload,
                  headers={"Authorization": f"Device {device.api_token}"}),
    )
    with scopes_disabled():
        assert await sync_to_async(OrderPosition.objects.filter(secret="foobarbaz").count)() == 1
        assert await sync_to_async(OrderPosition.objects.exclude(secret="foobarbaz").count)() == 1
    assert [r1, r2].count(201) == 2
