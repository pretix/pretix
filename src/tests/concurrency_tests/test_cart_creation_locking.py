import asyncio

import aiohttp
import pytest
from asgiref.sync import sync_to_async
from django_scopes import scopes_disabled

from pretix.base.models import CartPosition


@pytest.fixture
async def session(live_server, event):
    async with aiohttp.ClientSession() as session:
        yield session


async def post(session, url, data):
    async with session.post(url, data=data) as response:
        return await response.text()


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
