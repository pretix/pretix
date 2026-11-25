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
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled
from stripe import StripeObject

from pretix.base.models import (
    Event, Order, OrderPayment, OrderRefund, Organizer, Team, User,
)
from pretix.plugins.stripe.models import ReferencedStripeObject


@pytest.fixture
def env():
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy', plugins='pretix.plugins.stripe',
        date_from=now(), live=True
    )
    t = Team.objects.create(organizer=event.organizer, all_event_permissions=True)
    t.members.add(user)
    t.limit_events.add(event)
    o1 = Order.objects.create(
        code='FOOBAR', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=Decimal('13.37'),
        sales_channel=o.sales_channels.get(identifier="web"),
    )
    return event, o1


def get_test_charge(order: Order):
    return StripeObject.construct_from({
        "id": "ch_18TY6GGGWE2Is8TZHanef25",
        "object": "charge",
        "amount": 1337,
        "amount_refunded": 1000,
        "application_fee": None,
        "balance_transaction": "txn_18TY6GGGWE2Ias8TkwY6o51W",
        "captured": True,
        "created": 1467642664,
        "currency": "eur",
        "customer": None,
        "description": None,
        "destination": None,
        "dispute": None,
        "failure_code": None,
        "failure_message": None,
        "fraud_details": {},
        "invoice": None,
        "livemode": False,
        "metadata": {
            "code": order.code,
            "order": str(order.pk),
            "event": str(order.event.pk),
        },
        "order": None,
        "paid": True,
        "receipt_email": None,
        "receipt_number": None,
        "refunded": False,
        "refunds": {
            "object": "list",
            "data": [],
            "total_count": 0
        },
        "shipping": None,
        "payment_intent": {
            "id": "pi_123456",
            # Rest is ignored
        },
        "payment_method": "pm_654321",
        "payment_method_details": {
            "card": {
                "amount_authorized": 3500,
                "authorization_code": "12345",
                "brand": "visa",
                "checks": {
                    "address_line1_check": None,
                    "address_postal_code_check": "pass",
                    "cvc_check": "pass"
                },
                "country": "US",
                "exp_month": 12,
                "exp_year": 2034,
                "extended_authorization": {
                    "status": "disabled"
                },
                "fingerprint": "ABCDE",
                "funding": "credit",
                "incremental_authorization": {
                    "status": "unavailable"
                },
                "installments": None,
                "last4": "4242",
                "mandate": None,
                "multicapture": {
                    "status": "unavailable"
                },
                "network": "visa",
                "network_token": {
                    "used": False
                },
                "network_transaction_id": "12345",
                "overcapture": {
                    "maximum_amount_capturable": 3500,
                    "status": "unavailable"
                },
                "regulated_status": "unregulated",
                "three_d_secure": None,
                "transaction_link_id": None,
                "wallet": None
            },
            "type": "card"
        },
        "source": None,
        "source_transfer": None,
        "statement_descriptor": None,
        "status": "succeeded"
    }, None)


@pytest.mark.django_db
def test_webhook_all_good(env, client, monkeypatch):
    charge = get_test_charge(env[1])
    monkeypatch.setattr("stripe.Charge.retrieve", lambda *args, **kwargs: charge)

    client.post('/dummy/dummy/stripe/webhook/', json.dumps(
        {
            "id": "evt_18otImGGWE2Ias8TUyVRDB1G",
            "object": "event",
            "api_version": "2016-03-07",
            "created": 1472729052,
            "data": {
                "object": {
                    "id": "ch_18TY6GGGWE2Ias8TZHanef25",
                    "object": "charge",
                    # Rest of object is ignored anway
                }
            },
            "livemode": True,
            "pending_webhooks": 1,
            "request": "req_977XOWC8zk51Z9",
            "type": "charge.refunded"
        }
    ), content_type='application_json')

    order = env[1]
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_webhook_mark_paid(env, client, monkeypatch):
    order = env[1]
    order.status = Order.STATUS_PENDING
    order.save()
    charge = get_test_charge(env[1])
    charge["amount_refunded"] = 0
    with scopes_disabled():
        payment = env[1].payments.create(
            provider='stripe', amount=env[1].total, info='{}', state=OrderPayment.PAYMENT_STATE_CREATED,
        )
        ReferencedStripeObject.objects.create(
            order=order,
            payment=payment,
            reference="pi_123456",
        )

    monkeypatch.setattr("stripe.Charge.retrieve", lambda *args, **kwargs: charge)

    client.post('/dummy/dummy/stripe/webhook/', json.dumps(
        {
            "id": "evt_18otImGGWE2Ias8TUyVRDB1G",
            "object": "event",
            "api_version": "2016-03-07",
            "created": 1472729052,
            "data": {
                "object": {
                    "id": "ch_18TY6GGGWE2Ias8TZHanef25",
                    "object": "charge",
                    "payment_intent": "pi_123456",
                    "metadata": {
                        "event": order.event_id,
                    }
                    # Rest of object is ignored anway
                }
            },
            "livemode": True,
            "pending_webhooks": 1,
            "request": "req_977XOWC8zk51Z9",
            "type": "charge.succeeded"
        }
    ), content_type='application_json')

    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_webhook_partial_refund(env, client, monkeypatch):
    charge = get_test_charge(env[1])

    with scopes_disabled():
        payment = env[1].payments.create(
            provider='stripe', amount=env[1].total, info=json.dumps(charge)
        )
    ReferencedStripeObject.objects.create(order=env[1], reference="ch_18TY6GGGWE2Is8TZHanef25",
                                          payment=payment)

    charge['refunds'] = {
        "object": "list",
        "data": [
            {
                "id": "re_18otImGGWE2Ias8TY0QvwKYQ",
                "object": "refund",
                "amount": "12300",
                "balance_transaction": "txn_18otImGGWE2Ias8T4fLOxesC",
                "charge": "ch_18TY6GGGWE2Is8TZHanef25",
                "created": 1472729052,
                "currency": "eur",
                "metadata": {},
                "reason": None,
                "receipt_number": None,
                "status": "succeeded"
            }
        ],
        "total_count": 1
    }
    monkeypatch.setattr("stripe.Charge.retrieve", lambda *args, **kwargs: charge)

    r = client.post('/dummy/dummy/stripe/webhook/', json.dumps(
        {
            "id": "evt_18otImGGWE2Ias8TUyVRDB1G",
            "object": "event",
            "api_version": "2016-03-07",
            "created": 1472729052,
            "data": {
                "object": {
                    "id": "ch_18TY6GGGWE2Is8TZHanef25",
                    "object": "charge",
                    "payment_intent": "pi_123456",
                    # Rest of object is ignored anway
                }
            },
            "livemode": True,
            "pending_webhooks": 1,
            "request": "req_977XOWC8zk51Z9",
            "type": "charge.refunded"
        }
    ), content_type='application_json')
    print(r.content)

    order = env[1]
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID

    with scopes_disabled():
        ra = order.refunds.first()
    assert ra.state == OrderRefund.REFUND_STATE_EXTERNAL
    assert ra.source == 'external'
    assert ra.amount == Decimal('123.00')


@pytest.mark.django_db
def test_webhook_global(env, client, monkeypatch):
    order = env[1]
    order.status = Order.STATUS_PENDING
    order.save()

    charge = get_test_charge(env[1])
    charge["amount_refunded"] = 0
    monkeypatch.setattr("stripe.Charge.retrieve", lambda *args, **kwargs: charge)

    with scopes_disabled():
        payment = order.payments.create(
            provider='stripe', amount=order.total, info=json.dumps(charge), state=OrderPayment.PAYMENT_STATE_CREATED
        )
    ReferencedStripeObject.objects.create(order=order, reference="ch_18TY6GGGWE2Is8TZHanef25",
                                          payment=payment)
    ReferencedStripeObject.objects.create(order=order, reference="pi_123456",
                                          payment=payment)

    client.post('/_stripe/webhook/', json.dumps(
        {
            "id": "evt_18otImGGWE2Ias8TUyVRDB1G",
            "object": "event",
            "api_version": "2016-03-07",
            "created": 1472729052,
            "data": {
                "object": {
                    "id": "ch_18TY6GGGWE2Is8TZHanef25",
                    "object": "charge",
                    "payment_intent": "pi_123456",
                    "metadata": {
                        "event": order.event_id,
                    }
                    # Rest of object is ignored anway
                }
            },
            "livemode": True,
            "pending_webhooks": 1,
            "request": "req_977XOWC8zk51Z9",
            "type": "charge.succeeded"
        }
    ), content_type='application_json')

    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID
