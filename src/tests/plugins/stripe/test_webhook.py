import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

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
    t = Team.objects.create(organizer=event.organizer, can_view_orders=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)
    o1 = Order.objects.create(
        code='FOOBAR', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=Decimal('13.37'),
    )
    return event, o1


def get_test_charge(order: Order):
    return {
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
        "source": {
            "id": "card_18TY5wGGWE2Ias8Td38PjyPy",
            "object": "card",
            "address_city": None,
            "address_country": None,
            "address_line1": None,
            "address_line1_check": None,
            "address_line2": None,
            "address_state": None,
            "address_zip": None,
            "address_zip_check": None,
            "brand": "Visa",
            "country": "US",
            "customer": None,
            "cvc_check": "pass",
            "dynamic_last4": None,
            "exp_month": 12,
            "exp_year": 2016,
            "fingerprint": "FNbGTMaFvhRU2Y0E",
            "funding": "credit",
            "last4": "4242",
            "metadata": {},
            "name": "Carl Cardholder",
            "tokenization_method": None,
        },
        "source_transfer": None,
        "statement_descriptor": None,
        "status": "succeeded"
    }


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
def test_webhook_mark_paid_without_reference_and_payment(env, client, monkeypatch):
    order = env[1]
    order.status = Order.STATUS_PENDING
    order.save()

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
    ReferencedStripeObject.objects.create(order=env[1], reference="ch_18TY6GGGWE2Ias8TZHanef25",
                                          payment=payment)

    charge['refunds'] = {
        "object": "list",
        "data": [
            {
                "id": "re_18otImGGWE2Ias8TY0QvwKYQ",
                "object": "refund",
                "amount": "12300",
                "balance_transaction": "txn_18otImGGWE2Ias8T4fLOxesC",
                "charge": "ch_18TY6GGGWE2Ias8TZHanef25",
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
    monkeypatch.setattr("stripe.Charge.retrieve", lambda *args, **kwargs: charge)

    with scopes_disabled():
        payment = order.payments.create(
            provider='stripe', amount=order.total, info=json.dumps(charge), state=OrderPayment.PAYMENT_STATE_CREATED
        )
    ReferencedStripeObject.objects.create(order=order, reference="ch_18TY6GGGWE2Ias8TZHanef25",
                                          payment=payment)

    client.post('/_stripe/webhook/', json.dumps(
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
            "type": "charge.succeeded"
        }
    ), content_type='application_json')

    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_webhook_global_legacy_reference(env, client, monkeypatch):
    order = env[1]
    order.status = Order.STATUS_PENDING
    order.save()

    charge = get_test_charge(env[1])
    monkeypatch.setattr("stripe.Charge.retrieve", lambda *args, **kwargs: charge)

    with scopes_disabled():
        payment = order.payments.create(
            provider='stripe', amount=order.total, info=json.dumps(charge), state=OrderPayment.PAYMENT_STATE_CREATED
        )
    ReferencedStripeObject.objects.create(order=order, reference="ch_18TY6GGGWE2Ias8TZHanef25")

    client.post('/_stripe/webhook/', json.dumps(
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
            "type": "charge.succeeded"
        }
    ), content_type='application_json')

    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID
    with scopes_disabled():
        assert list(order.payments.all()) == [payment]
