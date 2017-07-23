import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now

from pretix.base.models import (
    Event, Order, Organizer, RequiredAction, Team, User,
)
from pretix.plugins.stripe.models import ReferencedStripeObject


@pytest.fixture
def env():
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), live=True
    )
    t = Team.objects.create(organizer=event.organizer, can_view_orders=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)
    o1 = Order.objects.create(
        code='FOOBAR', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=Decimal('13.37'), payment_provider='paypal',
        payment_info=json.dumps({
            "id": "PAY-5YK922393D847794YKER7MUI",
            "create_time": "2013-02-19T22:01:53Z",
            "update_time": "2013-02-19T22:01:55Z",
            "state": "approved",
            "intent": "sale",
            "payer": {
                "payment_method": "credit_card",
                "funding_instruments": [
                    {
                        "credit_card": {
                            "type": "mastercard",
                            "number": "xxxxxxxxxxxx5559",
                            "expire_month": 2,
                            "expire_year": 2018,
                            "first_name": "Betsy",
                            "last_name": "Buyer"
                        }
                    }
                ]
            },
            "transactions": [
                {
                    "amount": {
                        "total": "7.47",
                        "currency": "USD",
                        "details": {
                            "subtotal": "7.47"
                        }
                    },
                    "description": "This is the payment transaction description.",
                    "note_to_payer": "Contact us for any questions on your order.",
                    "related_resources": [
                        {
                            "sale": {
                                "id": "36C38912MN9658832",
                                "create_time": "2013-02-19T22:01:53Z",
                                "update_time": "2013-02-19T22:01:55Z",
                                "state": "completed",
                                "amount": {
                                    "total": "7.47",
                                    "currency": "USD"
                                },
                                "protection_eligibility": "ELIGIBLE",
                                "protection_eligibility_type": "ITEM_NOT_RECEIVED_ELIGIBLE",
                                "transaction_fee": {
                                    "value": "1.75",
                                    "currency": "USD"
                                },
                                "parent_payment": "PAY-5YK922393D847794YKER7MUI",
                                "links": [
                                    {
                                        "href": "https://api.paypal.com/v1/payments/sale/36C38912MN9658832",
                                        "rel": "self",
                                        "method": "GET"
                                    },
                                    {
                                        "href": "https://api.paypal.com/v1/payments/sale/36C38912MN9658832/refund",
                                        "rel": "refund",
                                        "method": "POST"
                                    },
                                    {
                                        "href":
                                            "https://api.paypal.com/v1/payments/payment/PAY-5YK922393D847794YKER7MUI",
                                        "rel": "parent_payment",
                                        "method": "GET"
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
            "links": [
                {
                    "href": "https://api.paypal.com/v1/payments/payment/PAY-5YK922393D847794YKER7MUI",
                    "rel": "self",
                    "method": "GET"
                }
            ]

        })
    )
    return event, o1


def get_test_charge(order: Order):
    return {
        "id": "36C38912MN9658832",
        "create_time": "2013-02-19T22:01:53Z",
        "update_time": "2013-02-19T22:01:55Z",
        "state": "completed",
        "amount": {
            "total": "7.47",
            "currency": "USD"
        },
        "protection_eligibility": "ELIGIBLE",
        "protection_eligibility_type": "ITEM_NOT_RECEIVED_ELIGIBLE,UNAUTHORIZED_PAYMENT_ELIGIBLE",
        "transaction_fee": {
            "value": "1.75",
            "currency": "USD"
        },
        "parent_payment": "PAY-5YK922393D847794YKER7MUI",
        "links": [
            {
                "href": "https://api.paypal.com/v1/payments/sale/36C38912MN9658832",
                "rel": "self",
                "method": "GET"
            },
            {
                "href": "https://api.paypal.com/v1/payments/sale/36C38912MN9658832/refund",
                "rel": "refund",
                "method": "POST"
            },
            {
                "href": "https://api.paypal.com/v1/payments/payment/PAY-5YK922393D847794YKER7MUI",
                "rel": "parent_payment",
                "method": "GET"
            }
        ]
    }


@pytest.mark.django_db
def test_webhook_all_good(env, client, monkeypatch):
    charge = get_test_charge(env[1])
    monkeypatch.setattr("paypalrestsdk.Sale.find", lambda *args: charge)
    monkeypatch.setattr("pretix.plugins.paypal.payment.Paypal.init_api", lambda *args: None)

    client.post('/dummy/dummy/paypal/webhook/', json.dumps(
        {
            "id": "WH-2WR32451HC0233532-67976317FL4543714",
            "create_time": "2014-10-23T17:23:52Z",
            "resource_type": "sale",
            "event_type": "PAYMENT.SALE.COMPLETED",
            "summary": "A successful sale payment was made for $ 0.48 USD",
            "resource": {
                "amount": {
                    "total": "-0.01",
                    "currency": "USD"
                },
                "id": "36C38912MN9658832",
                "parent_payment": "PAY-5YK922393D847794YKER7MUI",
                "update_time": "2014-10-31T15:41:51Z",
                "state": "completed",
                "create_time": "2014-10-31T15:41:51Z",
                "links": [],
                "sale_id": "9T0916710M1105906"
            },
            "links": [],
            "event_version": "1.0"
        }
    ), content_type='application_json')

    order = env[1]
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_webhook_global(env, client, monkeypatch):
    order = env[1]
    order.status = Order.STATUS_PENDING
    order.save()

    charge = get_test_charge(env[1])
    monkeypatch.setattr("paypalrestsdk.Sale.find", lambda *args: charge)
    monkeypatch.setattr("pretix.plugins.paypal.payment.Paypal.init_api", lambda *args: None)
    ReferencedStripeObject.objects.create(order=order, reference="PAY-5YK922393D847794YKER7MUI")

    client.post('/_paypal/webhook/', json.dumps(
        {
            "id": "WH-2WR32451HC0233532-67976317FL4543714",
            "create_time": "2014-10-23T17:23:52Z",
            "resource_type": "sale",
            "event_type": "PAYMENT.SALE.COMPLETED",
            "summary": "A successful sale payment was made for $ 0.48 USD",
            "resource": {
                "amount": {
                    "total": "-0.01",
                    "currency": "USD"
                },
                "id": "36C38912MN9658832",
                "parent_payment": "PAY-5YK922393D847794YKER7MUI",
                "update_time": "2014-10-31T15:41:51Z",
                "state": "completed",
                "create_time": "2014-10-31T15:41:51Z",
                "links": [],
                "sale_id": "9T0916710M1105906"
            },
            "links": [],
            "event_version": "1.0"
        }
    ), content_type='application_json')

    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_webhook_mark_paid(env, client, monkeypatch):
    order = env[1]
    order.status = Order.STATUS_PENDING
    order.save()

    charge = get_test_charge(env[1])
    monkeypatch.setattr("paypalrestsdk.Sale.find", lambda *args: charge)
    monkeypatch.setattr("pretix.plugins.paypal.payment.Paypal.init_api", lambda *args: None)

    client.post('/dummy/dummy/paypal/webhook/', json.dumps(
        {
            "id": "WH-2WR32451HC0233532-67976317FL4543714",
            "create_time": "2014-10-23T17:23:52Z",
            "resource_type": "sale",
            "event_type": "PAYMENT.SALE.COMPLETED",
            "summary": "A successful sale payment was made for $ 0.48 USD",
            "resource": {
                "amount": {
                    "total": "-0.01",
                    "currency": "USD"
                },
                "id": "36C38912MN9658832",
                "parent_payment": "PAY-5YK922393D847794YKER7MUI",
                "update_time": "2014-10-31T15:41:51Z",
                "state": "completed",
                "create_time": "2014-10-31T15:41:51Z",
                "links": [],
                "sale_id": "9T0916710M1105906"
            },
            "links": [],
            "event_version": "1.0"
        }
    ), content_type='application_json')

    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_webhook_refund1(env, client, monkeypatch):
    charge = get_test_charge(env[1])
    charge['state'] = 'refunded'

    monkeypatch.setattr("paypalrestsdk.Sale.find", lambda *args: charge)
    monkeypatch.setattr("pretix.plugins.paypal.payment.Paypal.init_api", lambda *args: None)

    client.post('/dummy/dummy/paypal/webhook/', json.dumps(
        {
            # Sample obtained in a sandbox webhook
            "id": "WH-9K829080KA1622327-31011919VC6498738",
            "create_time": "2017-01-15T20:15:36Z",
            "resource_type": "refund",
            "event_type": "PAYMENT.SALE.REFUNDED",
            "summary": "A EUR 255.41 EUR sale payment was refunded",
            "resource": {
                "amount": {
                    "total": "255.41",
                    "currency": "EUR"
                },
                "id": "75S46770PP192124D",
                "parent_payment": "PAY-5YK922393D847794YKER7MUI",
                "update_time": "2017-01-15T20:15:06Z",
                "create_time": "2017-01-15T20:14:29Z",
                "state": "completed",
                "links": [],
                "refund_to_payer": {
                    "value": "255.41",
                    "currency": "EUR"
                },
                "invoice_number": "",
                "refund_reason_code": "REFUND",
                "sale_id": "9T0916710M1105906"
            },
            "links": [],
            "event_version": "1.0"
        }
    ), content_type='application_json')

    order = env[1]
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID

    ra = RequiredAction.objects.get(action_type="pretix.plugins.paypal.refund")
    client.login(username='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/paypal/refund/{}/'.format(ra.pk))

    order = env[1]
    order.refresh_from_db()
    assert order.status == Order.STATUS_REFUNDED


@pytest.mark.django_db
def test_webhook_refund2(env, client, monkeypatch):
    charge = get_test_charge(env[1])
    charge['state'] = 'refunded'

    monkeypatch.setattr("paypalrestsdk.Sale.find", lambda *args: charge)
    monkeypatch.setattr("pretix.plugins.paypal.payment.Paypal.init_api", lambda *args: None)

    client.post('/dummy/dummy/paypal/webhook/', json.dumps(
        {
            # Sample obtained in the webhook simulator
            "id": "WH-2N242548W9943490U-1JU23391CS4765624",
            "create_time": "2014-10-31T15:42:24Z",
            "resource_type": "sale",
            "event_type": "PAYMENT.SALE.REFUNDED",
            "summary": "A 0.01 USD sale payment was refunded",
            "resource": {
                "amount": {
                    "total": "-0.01",
                    "currency": "USD"
                },
                "id": "36C38912MN9658832",
                "parent_payment": "PAY-5YK922393D847794YKER7MUI",
                "update_time": "2014-10-31T15:41:51Z",
                "state": "completed",
                "create_time": "2014-10-31T15:41:51Z",
                "links": [],
                "sale_id": "9T0916710M1105906"
            },
            "links": [],
            "event_version": "1.0"
        }
    ), content_type='application_json')

    order = env[1]
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID

    ra = RequiredAction.objects.get(action_type="pretix.plugins.paypal.refund")
    client.login(username='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/paypal/refund/{}/'.format(ra.pk))

    order = env[1]
    order.refresh_from_db()
    assert order.status == Order.STATUS_REFUNDED
