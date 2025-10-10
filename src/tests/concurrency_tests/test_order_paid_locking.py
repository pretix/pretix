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
from decimal import Decimal
from importlib import import_module

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.concurrency_tests.utils import get

from pretix.base.models import Order, OrderPayment, OrderPosition

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore


@pytest.fixture
@scopes_disabled()
def order1_expired(event, organizer, item):
    order = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_EXPIRED, locale='en',
        datetime=now(), expires=now() - timedelta(days=10),
        sales_channel=organizer.sales_channels.get(identifier="web"),
        total=Decimal('0.00'),
    )
    OrderPosition.objects.create(
        order=order, item=item, variation=None,
        price=Decimal("0.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
    )
    p = OrderPayment.objects.create(
        order=order, amount=Decimal("0.00"), provider="free", state=OrderPayment.PAYMENT_STATE_CREATED,
    )
    return order, p


@pytest.fixture
@scopes_disabled()
def order2_expired(event, organizer, item, customer):
    order = Order.objects.create(
        code='BAR', event=event, email='dummy@dummy.test',
        status=Order.STATUS_EXPIRED, locale='en',
        datetime=now(), expires=now() - timedelta(days=10),
        sales_channel=organizer.sales_channels.get(identifier="web"),
        total=Decimal('0.00'),
    )
    OrderPosition.objects.create(
        order=order, item=item, variation=None,
        price=Decimal("0.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
    )
    p = OrderPayment.objects.create(
        order=order, amount=Decimal("0.00"), provider="free", state=OrderPayment.PAYMENT_STATE_CREATED,
    )
    return order, p


@pytest.mark.asyncio
async def test_quota_race_condition_happens_if_we_disable_locks(live_server, session, event, item, quota,
                                                                order1_expired, order2_expired):
    # This test exists to ensure that our test setup makes sense. If it fails, all tests down below
    # might be useless.
    quota.size = 1
    await sync_to_async(quota.save)()

    url1 = f"/{event.organizer.slug}/{event.slug}/order/{order1_expired[0].code}/{order1_expired[0].secret}/" \
           f"pay/{order1_expired[1].pk}/complete?_debug_flag=skip-csrf&_debug_flag=skip-locking&_debug_flag=sleep-after-quota-check"
    url2 = f"/{event.organizer.slug}/{event.slug}/order/{order2_expired[0].code}/{order2_expired[0].secret}/" \
           f"pay/{order2_expired[1].pk}/complete?_debug_flag=skip-csrf&_debug_flag=skip-locking&_debug_flag=sleep-after-quota-check"
    await asyncio.gather(
        get(session, f"{live_server}{url1}"),
        get(session, f"{live_server}{url2}"),
    )
    await sync_to_async(order1_expired[0].refresh_from_db)()
    await sync_to_async(order2_expired[0].refresh_from_db)()
    assert {order1_expired[0].status, order2_expired[0].status} == {Order.STATUS_PAID}


@pytest.mark.asyncio
async def test_quota_race_condition_happens_prevented_by_lock(live_server, session, event, item, quota, order1_expired, order2_expired):
    quota.size = 1
    await sync_to_async(quota.save)()

    url1 = f"/{event.organizer.slug}/{event.slug}/order/{order1_expired[0].code}/{order1_expired[0].secret}/" \
           f"pay/{order1_expired[1].pk}/complete?_debug_flag=skip-csrf&_debug_flag=sleep-after-quota-check"
    url2 = f"/{event.organizer.slug}/{event.slug}/order/{order2_expired[0].code}/{order2_expired[0].secret}/" \
           f"pay/{order2_expired[1].pk}/complete?_debug_flag=skip-csrf&_debug_flag=sleep-after-quota-check"
    await asyncio.gather(
        get(session, f"{live_server}{url1}"),
        get(session, f"{live_server}{url2}"),
    )
    await sync_to_async(order1_expired[0].refresh_from_db)()
    await sync_to_async(order2_expired[0].refresh_from_db)()
    assert {order1_expired[0].status, order2_expired[0].status} == {Order.STATUS_PAID, Order.STATUS_EXPIRED}
