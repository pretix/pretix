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
import datetime
import json
from decimal import Decimal

import freezegun
import pytest
from django_scopes import scopes_disabled

from pretix.base.models import Order, OrderPosition
from pretix.base.models.orders import OrderFee


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def taxrule(event):
    return event.tax_rules.create(rate=Decimal("19.00"), code="S/standard")


@pytest.fixture
def order(event, item, device, taxrule):
    with freezegun.freeze_time("2017-12-01T10:00:00"):
        o = Order.objects.create(
            code="FOO",
            event=event,
            email="dummy@dummy.test",
            status=Order.STATUS_PENDING,
            secret="k24fiuwvu8kxz3y1",
            datetime=datetime.datetime(
                2017, 12, 1, 10, 0, 0, tzinfo=datetime.timezone.utc
            ),
            expires=datetime.datetime(
                2017, 12, 10, 10, 0, 0, tzinfo=datetime.timezone.utc
            ),
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
            total=23,
            locale="en",
        )
        o.fees.create(
            fee_type=OrderFee.FEE_TYPE_PAYMENT,
            value=Decimal("0.25"),
            tax_rate=Decimal("19.00"),
            tax_value=Decimal("0.05"),
            tax_rule=taxrule,
            tax_code=taxrule.code,
        )
        OrderPosition.objects.create(
            order=o,
            item=item,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={"full_name": "Peter", "_scheme": "full"},
            secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
            pseudonymization_id="ABCDEFGHKL",
            positionid=1,
        )
        o.create_transactions()
        return o


TEST_TRANSACTION_RES_OP = {
    "count": 1,
    "created": "2017-12-01T10:00:00Z",
    "datetime": "2017-12-01T10:00:00Z",
    "fee_type": None,
    "internal_type": None,
    "item": None,
    "order": "FOO",
    "positionid": 1,
    "price": "23.00",
    "subevent": None,
    "tax_code": None,
    "tax_rate": "0.00",
    "tax_rule": None,
    "tax_value": "0.00",
    "variation": None,
}
TEST_TRANSACTION_RES_FEE = {
    "count": 1,
    "created": "2017-12-01T10:00:00Z",
    "datetime": "2017-12-01T10:00:00Z",
    "fee_type": "payment",
    "internal_type": "",
    "item": None,
    "order": "FOO",
    "positionid": None,
    "price": "0.25",
    "subevent": None,
    "tax_code": "S/standard",
    "tax_rate": "19.00",
    "tax_rule": 1,
    "tax_value": "0.05",
    "variation": None,
}


@pytest.mark.django_db
def test_transaction_list(token_client, organizer, event, order, item, taxrule):
    res_op = copy.deepcopy(TEST_TRANSACTION_RES_OP)
    res_fee = copy.deepcopy(TEST_TRANSACTION_RES_FEE)
    with scopes_disabled():
        res_fee["id"] = order.transactions.get(fee_type="payment").pk
        res_fee["tax_rule"] = taxrule.pk
        res_op["id"] = order.transactions.get(item__isnull=False).pk
        res_op["item"] = item.pk

    resp = token_client.get(
        "/api/v1/organizers/{}/events/{}/transactions/".format(
            organizer.slug,
            event.slug,
        )
    )
    assert resp.status_code == 200
    assert res_op in resp.data["results"]
    assert res_fee in resp.data["results"]
    assert resp.data["count"] == 2

    resp = token_client.get(
        "/api/v1/organizers/{}/events/{}/transactions/?order=FOO".format(
            organizer.slug,
            event.slug,
        )
    )
    assert resp.data["count"] == 2
    resp = token_client.get(
        "/api/v1/organizers/{}/events/{}/transactions/?order=BAR".format(
            organizer.slug,
            event.slug,
        )
    )
    assert resp.data["count"] == 0

    resp = token_client.get(
        "/api/v1/organizers/{}/events/{}/transactions/?datetime_since=2017-12-01T09:00:00Z".format(
            organizer.slug,
            event.slug,
        )
    )
    assert resp.data["count"] == 2
    resp = token_client.get(
        "/api/v1/organizers/{}/events/{}/transactions/?datetime_since=2017-12-02T09:00:00Z".format(
            organizer.slug,
            event.slug,
        )
    )
    assert resp.data["count"] == 0

    resp = token_client.get(
        "/api/v1/organizers/{}/events/{}/transactions/?item={}".format(
            organizer.slug, event.slug, item.pk
        )
    )
    assert resp.data["count"] == 1
    assert res_op in resp.data["results"]

    resp = token_client.get(
        "/api/v1/organizers/{}/events/{}/transactions/?fee_type={}".format(
            organizer.slug, event.slug, "payment"
        )
    )
    assert resp.data["count"] == 1
    assert res_fee in resp.data["results"]


@pytest.mark.django_db
def test_order_detail(token_client, organizer, event, order, item, taxrule):
    res_fee = copy.deepcopy(TEST_TRANSACTION_RES_FEE)
    with scopes_disabled():
        tx = order.transactions.get(fee_type="payment")
        res_fee["id"] = tx.pk
        res_fee["tax_rule"] = taxrule.pk
    resp = token_client.get(
        "/api/v1/organizers/{}/events/{}/transactions/{}/".format(
            organizer.slug, event.slug, tx.pk
        )
    )
    assert resp.status_code == 200
    assert json.loads(json.dumps(res_fee)) == json.loads(json.dumps(resp.data))


@pytest.mark.django_db
def test_organizer_list(token_client, team, organizer, event, order, item, taxrule):
    resp = token_client.get(
        "/api/v1/organizers/{}/transactions/".format(
            organizer.slug,
        )
    )
    assert resp.status_code == 200
    assert resp.data["count"] == 2
    assert "event" in resp.data["results"][0]

    resp = token_client.get(
        "/api/v1/organizers/{}/transactions/?event=dummy".format(
            organizer.slug,
        )
    )
    assert resp.status_code == 200
    assert resp.data["count"] == 2

    resp = token_client.get(
        "/api/v1/organizers/{}/transactions/?event=test".format(
            organizer.slug,
        )
    )
    assert resp.status_code == 200
    assert resp.data["count"] == 0

    team.all_events = False
    team.save()

    resp = token_client.get(
        "/api/v1/organizers/{}/transactions/".format(
            organizer.slug,
        )
    )
    assert resp.status_code == 200
    assert resp.data["count"] == 0

    team.all_events = True
    team.can_view_orders = False
    team.save()

    resp = token_client.get(
        "/api/v1/organizers/{}/transactions/".format(
            organizer.slug,
        )
    )
    assert resp.status_code == 200
    assert resp.data["count"] == 0
