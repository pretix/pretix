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
from datetime import timedelta
from importlib import import_module

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.concurrency_tests.utils import post

from pretix.base.models import CartPosition, OrderPosition

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore


@pytest.fixture
@scopes_disabled()
def cart1_expired(event, organizer, item, customer):
    cp = CartPosition.objects.create(
        event=event,
        item=item,
        datetime=now(),
        expires=now() - timedelta(days=1),
        price=item.default_price,
        cart_id="cart1"
    )
    session = SessionStore("cart1")
    session['current_cart_event_{}'.format(event.pk)] = "cart1"
    session['carts'] = {
        'cart1': {
            'payment': 'banktransfer',
            'email': 'admin@localhost',
            'customer': customer.pk,
        }
    }
    session[f'customer_auth_id:{event.organizer.pk}'] = customer.pk
    session[f'customer_auth_hash:{event.organizer.pk}'] = customer.get_session_auth_hash()
    session.save()
    return cp, session


@pytest.fixture
@scopes_disabled()
def cart2_expired(event, organizer, item, customer):
    cp = CartPosition.objects.create(
        event=event,
        item=item,
        datetime=now(),
        expires=now() - timedelta(days=1),
        price=item.default_price,
        cart_id="cart2"
    )
    session = SessionStore("cart2")
    session['current_cart_event_{}'.format(event.pk)] = "cart2"
    session['carts'] = {
        'cart2': {
            'payment': 'banktransfer',
            'email': 'admin@localhost',
            'customer': customer.pk,
        }
    }
    session[f'customer_auth_id:{event.organizer.pk}'] = customer.pk
    session[f'customer_auth_hash:{event.organizer.pk}'] = customer.get_session_auth_hash()
    session.save()
    return cp, session


@pytest.mark.asyncio
async def test_quota_race_condition_happens_if_we_disable_locks(live_server, session, event, item, quota,
                                                                cart1_expired, cart2_expired):
    # This test exists to ensure that our test setup makes sense. If it fails, all tests down below
    # might be useless.
    quota.size = 1
    await sync_to_async(quota.save)()

    url = f"/{event.organizer.slug}/{event.slug}/checkout/confirm/?_debug_flag=skip-csrf&_debug_flag=skip-locking&_debug_flag=sleep-after-quota-check"
    payload = {}

    r1, r2 = await asyncio.gather(
        post(session, f"{live_server}{url}", data=payload, cookies={settings.SESSION_COOKIE_NAME: cart1_expired[1].session_key}),
        post(session, f"{live_server}{url}", data=payload, cookies={settings.SESSION_COOKIE_NAME: cart2_expired[1].session_key}),
    )
    assert ['thank-you' in r1, 'thank-you' in r2].count(True) == 2
    with scopes_disabled():
        assert await sync_to_async(CartPosition.objects.filter(item=item).count)() == 0
        assert await sync_to_async(OrderPosition.objects.filter(item=item).count)() == 2


@pytest.mark.asyncio
async def test_quota_race_condition_prevented_by_locks(live_server, session, event, item, quota, cart1_expired, cart2_expired):
    quota.size = 1
    await sync_to_async(quota.save)()

    url = f"/{event.organizer.slug}/{event.slug}/checkout/confirm/?_debug_flag=skip-csrf&_debug_flag=sleep-after-quota-check"
    payload = {}

    r1, r2 = await asyncio.gather(
        post(session, f"{live_server}{url}", data=payload, cookies={settings.SESSION_COOKIE_NAME: cart1_expired[1].session_key}),
        post(session, f"{live_server}{url}", data=payload, cookies={settings.SESSION_COOKIE_NAME: cart2_expired[1].session_key}),
    )
    assert ['thank-you' in r1, 'thank-you' in r2].count(True) == 1
    with scopes_disabled():
        assert await sync_to_async(OrderPosition.objects.filter(item=item).count)() == 1
        assert await sync_to_async(CartPosition.objects.filter(item=item).count)() == 0


@pytest.mark.asyncio
async def test_voucher_race_condition_prevented_by_locks(live_server, session, event, item, quota, cart1_expired, cart2_expired, voucher):
    cart1_expired[0].voucher = voucher
    await sync_to_async(cart1_expired[0].save)()
    cart2_expired[0].voucher = voucher
    await sync_to_async(cart2_expired[0].save)()

    url = f"/{event.organizer.slug}/{event.slug}/checkout/confirm/?_debug_flag=skip-csrf&_debug_flag=sleep-after-quota-check"
    payload = {}

    r1, r2 = await asyncio.gather(
        post(session, f"{live_server}{url}", data=payload, cookies={settings.SESSION_COOKIE_NAME: cart1_expired[1].session_key}),
        post(session, f"{live_server}{url}", data=payload, cookies={settings.SESSION_COOKIE_NAME: cart2_expired[1].session_key}),
    )
    assert ['thank-you' in r1, 'thank-you' in r2].count(True) == 1
    with scopes_disabled():
        assert await sync_to_async(OrderPosition.objects.filter(item=item, voucher=voucher).count)() == 1
        assert await sync_to_async(CartPosition.objects.filter(item=item, voucher=voucher).count)() == 0


@pytest.mark.asyncio
async def test_seat_race_condition_prevented_by_locks(live_server, session, event, item, quota, cart1_expired, cart2_expired, seat):
    cart1_expired[0].seat = seat
    await sync_to_async(cart1_expired[0].save)()
    cart2_expired[0].seat = seat
    await sync_to_async(cart2_expired[0].save)()

    url = f"/{event.organizer.slug}/{event.slug}/checkout/confirm/?_debug_flag=skip-csrf&_debug_flag=sleep-after-quota-check"
    payload = {}

    r1, r2 = await asyncio.gather(
        post(session, f"{live_server}{url}", data=payload, cookies={settings.SESSION_COOKIE_NAME: cart1_expired[1].session_key}),
        post(session, f"{live_server}{url}", data=payload, cookies={settings.SESSION_COOKIE_NAME: cart2_expired[1].session_key}),
    )
    assert ['thank-you' in r1, 'thank-you' in r2].count(True) == 1
    with scopes_disabled():
        assert await sync_to_async(OrderPosition.objects.filter(item=item, seat=seat).count)() == 1
        assert await sync_to_async(CartPosition.objects.filter(item=item, seat=seat).count)() == 0


@pytest.mark.asyncio
async def test_membership_race_condition_prevented_by_locks(live_server, session, event, item, quota, cart1_expired, cart2_expired, membership):
    cart1_expired[0].used_membership = membership
    await sync_to_async(cart1_expired[0].save)()
    cart2_expired[0].used_membership = membership
    await sync_to_async(cart2_expired[0].save)()
    item.require_membership = True
    await sync_to_async(item.save)()
    await sync_to_async(item.require_membership_types.set)([membership.membership_type])

    url = f"/{event.organizer.slug}/{event.slug}/checkout/confirm/?_debug_flag=skip-csrf&_debug_flag=sleep-after-quota-check"
    payload = {}

    r1, r2 = await asyncio.gather(
        post(session, f"{live_server}{url}", data=payload, cookies={settings.SESSION_COOKIE_NAME: cart1_expired[1].session_key}),
        post(session, f"{live_server}{url}", data=payload, cookies={settings.SESSION_COOKIE_NAME: cart2_expired[1].session_key}),
    )
    assert ['thank-you' in r1, 'thank-you' in r2].count(True) == 1
    with scopes_disabled():
        assert await sync_to_async(OrderPosition.objects.filter(item=item).count)() == 1
        assert await sync_to_async(CartPosition.objects.filter(item=item).count)() == 1
