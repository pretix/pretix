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
import copy
from datetime import timedelta

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.api.test_order_create import ORDER_CREATE_PAYLOAD

from pretix.base.models import Order, OrderPayment
from pretix.base.signals import order_paid, order_placed
from pretix.plugins.autocheckin.models import AutoCheckinRule


@pytest.fixture
@scopes_disabled()
def order(organizer, event, item):
    order = Order.objects.create(
        event=event,
        status=Order.STATUS_PENDING,
        expires=now() + timedelta(days=3),
        sales_channel=organizer.sales_channels.get(identifier="web"),
        total=4,
    )
    order.positions.create(order=order, item=item, price=2)
    return order


@pytest.mark.django_db
@scopes_disabled()
def test_sales_channel_all(event, item, order, checkin_list):
    event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PLACED,
        all_sales_channels=True,
    )
    order_placed.send(event, order=order, bulk=False)
    assert order.positions.first().checkins.exists()


@pytest.mark.django_db
@scopes_disabled()
def test_sales_channel_limit(event, item, order, checkin_list):
    acr = event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PLACED,
        all_sales_channels=False,
    )

    order_placed.send(event, order=order, bulk=False)
    assert not order.positions.first().checkins.exists()

    acr.limit_sales_channels.add(order.sales_channel)

    order_placed.send(event, order=order, bulk=False)
    assert order.positions.first().checkins.exists()


@pytest.mark.django_db
@scopes_disabled()
def test_items_all(event, item, order, checkin_list):
    event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PLACED,
        all_products=True,
    )
    order_placed.send(event, order=order, bulk=False)
    assert order.positions.first().checkins.exists()


@pytest.mark.django_db
@scopes_disabled()
def test_items_limit(event, item, order, checkin_list):
    acr = event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PLACED,
        all_products=False,
    )

    order_placed.send(event, order=order, bulk=False)
    assert not order.positions.first().checkins.exists()

    acr.limit_products.add(item)

    order_placed.send(event, order=order, bulk=False)
    assert order.positions.first().checkins.exists()


@pytest.mark.django_db
@scopes_disabled()
def test_variations_limit_mixed_order(event, item, order, checkin_list):
    var = item.variations.create(value="V1")
    op = order.positions.first()
    op.variation = var
    op.save()

    var2 = item.variations.create(value="V2")
    order.positions.create(order=order, item=item, price=2, variation=var2)

    acr = event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PLACED,
        all_products=False,
    )
    acr.limit_variations.add(var)

    order_placed.send(event, order=order, bulk=False)
    assert order.positions.first().checkins.exists()
    assert not order.positions.last().checkins.exists()


@pytest.mark.django_db
@scopes_disabled()
def test_variations_limit(event, item, order, checkin_list):
    var = item.variations.create(value="V1")
    op = order.positions.first()
    op.variation = var
    op.save()

    acr = event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PLACED,
        all_products=False,
    )

    order_placed.send(event, order=order, bulk=False)
    assert not order.positions.first().checkins.exists()

    acr.limit_variations.add(var)

    order_placed.send(event, order=order, bulk=False)
    assert order.positions.first().checkins.exists()

    order.positions.first().checkins.all().delete()
    acr.limit_products.add(item)
    acr.limit_variations.clear()

    order_placed.send(event, order=order, bulk=False)
    assert order.positions.first().checkins.exists()


@pytest.mark.django_db
@scopes_disabled()
def test_mode_placed(event, item, order, checkin_list):
    event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PLACED,
    )

    order_paid.send(event, order=order)
    assert not order.positions.first().checkins.exists()

    order_placed.send(event, order=order, bulk=False)
    assert order.positions.first().checkins.exists()


@pytest.mark.django_db
@scopes_disabled()
def test_mode_paid(event, item, order, checkin_list):
    event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PAID,
    )

    order_placed.send(event, order=order, bulk=False)
    assert not order.positions.first().checkins.exists()

    order_paid.send(event, order=order)
    assert order.positions.first().checkins.exists()


@pytest.mark.django_db
@scopes_disabled()
def test_payment_provider_limit(event, item, order, checkin_list):
    event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PAID,
        all_payment_methods=False,
        limit_payment_methods=["manual"],
    )

    p = order.payments.create(
        amount=order.total,
        state=OrderPayment.PAYMENT_STATE_CONFIRMED,
        provider="banktransfer",
    )

    order_paid.send(event, order=order)
    assert not order.positions.first().checkins.exists()

    p.provider = "manual"
    p.save()
    order_paid.send(event, order=order)
    assert order.positions.first().checkins.exists()


@pytest.mark.django_db
@scopes_disabled()
def test_idempodency(event, item, order, checkin_list):
    event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PAID,
    )
    order_paid.send(event, order=order)
    assert order.positions.first().checkins.count() == 1
    order_paid.send(event, order=order)
    assert order.positions.first().checkins.count() == 1


@pytest.mark.django_db
@scopes_disabled()
def test_multiple_rules_same_list(event, item, order, checkin_list):
    event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PAID,
    )
    event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PAID,
    )
    order_paid.send(event, order=order)
    assert order.positions.first().checkins.count() == 1


@pytest.mark.django_db
@scopes_disabled()
def test_multiple_rules_different_lists(event, item, order, checkin_list):
    cl2 = event.checkin_lists.create(name="bar")
    event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PAID,
    )
    event.autocheckinrule_set.create(
        list=cl2,
        mode=AutoCheckinRule.MODE_PAID,
    )
    order_paid.send(event, order=order)
    assert order.positions.first().checkins.count() == 2


@pytest.mark.django_db
@scopes_disabled()
def test_autodetect_lists(event, item, order, checkin_list):
    cl2 = event.checkin_lists.create(name="bar", all_products=False)
    cl2.limit_products.add(item)
    event.checkin_lists.create(name="baz", all_products=False)

    event.autocheckinrule_set.create(
        mode=AutoCheckinRule.MODE_PAID,
    )
    order_paid.send(event, order=order)

    assert {c.list_id for c in order.positions.first().checkins.all()} == {
        checkin_list.pk,
        cl2.pk,
    }


@pytest.mark.django_db
@scopes_disabled()
def test_order_create_via_api_placed(
    token_client, organizer, event, item, checkin_list
):
    acr = event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PLACED,
        all_sales_channels=False,
    )
    acr.limit_sales_channels.add(organizer.sales_channels.get(identifier="web"))

    q = event.quotas.create(name="Foo", size=None)
    q.items.add(item)

    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res["positions"][0]["item"] = item.pk
    res["positions"][0]["answers"] = []
    resp = token_client.post(
        "/api/v1/organizers/{}/events/{}/orders/".format(organizer.slug, event.slug),
        format="json",
        data=res,
    )
    assert resp.status_code == 201

    o = Order.objects.get(code=resp.data["code"])
    assert o.positions.first().checkins.first().auto_checked_in


@pytest.mark.django_db
@scopes_disabled()
def test_order_create_via_api_paid(token_client, organizer, event, item, checkin_list):
    event.autocheckinrule_set.create(
        list=checkin_list,
        mode=AutoCheckinRule.MODE_PAID,
        all_payment_methods=False,
        limit_payment_methods=["manual"],
    )
    q = event.quotas.create(name="Foo", size=None)
    q.items.add(item)

    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res["positions"][0]["item"] = item.pk
    res["positions"][0]["answers"] = []
    res["status"] = "p"
    res["payment_provider"] = "manual"
    resp = token_client.post(
        "/api/v1/organizers/{}/events/{}/orders/".format(organizer.slug, event.slug),
        format="json",
        data=res,
    )
    assert resp.status_code == 201

    o = Order.objects.get(code=resp.data["code"])
    assert o.positions.first().checkins.first().auto_checked_in
