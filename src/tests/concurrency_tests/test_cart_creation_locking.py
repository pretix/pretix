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
from tests.concurrency_tests.utils import post

from pretix.base.models import CartPosition


@pytest.mark.asyncio
async def test_quota_race_condition_happens_if_we_disable_locks(live_server, session, event, item, quota):
    # This test exists to ensure that our test setup makes sense. If it fails, all tests down below
    # might be useless.
    quota.size = 1
    await sync_to_async(quota.save)()

    url = f"/{event.organizer.slug}/{event.slug}/cart/add?_debug_flag=skip-csrf&_debug_flag=skip-locking&_debug_flag=sleep-after-quota-check"
    payload = {
        f'item_{item.pk}': '1',
    }

    r1, r2 = await asyncio.gather(
        post(session, f"{live_server}{url}", data=payload),
        post(session, f"{live_server}{url}", data=payload)
    )
    assert ['alert-success' in r1, 'alert-success' in r2].count(True) == 2
    with scopes_disabled():
        assert await sync_to_async(CartPosition.objects.filter(item=item).count)() == 2


@pytest.mark.asyncio
async def test_cart_race_condition_prevented_by_locks(live_server, session, event, item, quota):
    quota.size = 1
    await sync_to_async(quota.save)()

    url = f"/{event.organizer.slug}/{event.slug}/cart/add?_debug_flag=skip-csrf&_debug_flag=sleep-after-quota-check"
    payload = {
        f'item_{item.pk}': '1',
    }

    r1, r2 = await asyncio.gather(
        post(session, f"{live_server}{url}", data=payload),
        post(session, f"{live_server}{url}", data=payload)
    )
    assert ['alert-success' in r1, 'alert-success' in r2].count(True) == 1
    with scopes_disabled():
        assert await sync_to_async(CartPosition.objects.filter(item=item).count)() == 1


@pytest.mark.asyncio
async def test_cart_race_condition_possible_in_repeatable_read(live_server, session, event, item, quota):
    quota.size = 1
    await sync_to_async(quota.save)()

    url = f"/{event.organizer.slug}/{event.slug}/cart/add?_debug_flag=skip-csrf&_debug_flag=repeatable-read&_debug_flag=sleep-before-commit"
    payload = {
        f'item_{item.pk}': '1',
    }

    r1, r2 = await asyncio.gather(
        post(session, f"{live_server}{url}", data=payload),
        post(session, f"{live_server}{url}", data=payload)
    )
    assert ['alert-success' in r1, 'alert-success' in r2].count(True) == 2
    with scopes_disabled():
        assert await sync_to_async(CartPosition.objects.filter(item=item).count)() == 2


@pytest.mark.asyncio
async def test_cart_race_condition_prevented_by_read_committed(live_server, session, event, item, quota):
    quota.size = 1
    await sync_to_async(quota.save)()

    url = f"/{event.organizer.slug}/{event.slug}/cart/add?_debug_flag=skip-csrf&_debug_flag=sleep-before-commit"
    payload = {
        f'item_{item.pk}': '1',
    }

    r1, r2 = await asyncio.gather(
        post(session, f"{live_server}{url}", data=payload),
        post(session, f"{live_server}{url}", data=payload)
    )
    assert ['alert-success' in r1, 'alert-success' in r2].count(True) == 1
    with scopes_disabled():
        assert await sync_to_async(CartPosition.objects.filter(item=item).count)() == 1


@pytest.mark.asyncio
async def test_cart_voucher_race_condition_prevented_by_locks(live_server, session, event, item, quota, voucher):
    url = f"/{event.organizer.slug}/{event.slug}/cart/add?_debug_flag=skip-csrf&_debug_flag=sleep-after-quota-check"
    payload = {
        f'item_{item.pk}': '1',
        '_voucher_code': voucher.code,
    }

    r1, r2 = await asyncio.gather(
        post(session, f"{live_server}{url}", data=payload),
        post(session, f"{live_server}{url}", data=payload)
    )
    assert ['alert-success' in r1, 'alert-success' in r2].count(True) == 1
    with scopes_disabled():
        assert await sync_to_async(CartPosition.objects.filter(item=item, voucher=voucher).count)() == 1


@pytest.mark.asyncio
async def test_cart_seat_race_condition_prevented_by_locks(live_server, session, event, item, quota, seat):
    url = f"/{event.organizer.slug}/{event.slug}/cart/add?_debug_flag=skip-csrf&_debug_flag=sleep-after-quota-check"
    payload = {
        f'seat_{item.pk}': seat.seat_guid,
    }

    r1, r2 = await asyncio.gather(
        post(session, f"{live_server}{url}", data=payload),
        post(session, f"{live_server}{url}", data=payload)
    )
    assert ['alert-success' in r1, 'alert-success' in r2].count(True) == 1
    with scopes_disabled():
        assert await sync_to_async(CartPosition.objects.filter(item=item, seat=seat).count)() == 1
