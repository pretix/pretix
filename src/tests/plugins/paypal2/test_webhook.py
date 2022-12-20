#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
from paypalhttp.http_response import Result

from pretix.base.models import (
    Event, Order, OrderPayment, OrderRefund, Organizer, Team, User,
)
from pretix.plugins.paypal.models import ReferencedPayPalObject


@pytest.fixture
def env():
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy', plugins='pretix.plugins.paypal2',
        date_from=now(), live=True
    )
    t = Team.objects.create(organizer=event.organizer, can_view_orders=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)
    o1 = Order.objects.create(
        code='FOOBAR', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=Decimal('43.59'),
    )
    o1.payments.create(
        amount=o1.total,
        provider='paypal',
        state=OrderPayment.PAYMENT_STATE_CONFIRMED,
        info=json.dumps({
            "id": "806440346Y391300T",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "reference_id": "default",
                    "shipping": {
                        "name": {
                            "full_name": "test buyer"
                        }
                    },
                    "payments": {
                        "captures": [
                            {
                                "id": "22A4162004478570J",
                                "status": "COMPLETED",
                                "amount": {
                                    "currency_code": "EUR",
                                    "value": "43.59"
                                },
                                "final_capture": True,
                                "disbursement_mode": "INSTANT",
                                "seller_protection": {
                                    "status": "ELIGIBLE",
                                    "dispute_categories": [
                                        "ITEM_NOT_RECEIVED",
                                        "UNAUTHORIZED_TRANSACTION"
                                    ]
                                },
                                "seller_receivable_breakdown": {
                                    "gross_amount": {
                                        "currency_code": "EUR",
                                        "value": "43.59"
                                    },
                                    "paypal_fee": {
                                        "currency_code": "EUR",
                                        "value": "1.18"
                                    },
                                    "net_amount": {
                                        "currency_code": "EUR",
                                        "value": "42.41"
                                    }
                                },
                                "custom_id": "Order PAYPALV2-JWJGC",
                                "links": [
                                    {
                                        "href": "https://api.sandbox.paypal.com/v2/payments/captures/22A4162004478570J",
                                        "rel": "self",
                                        "method": "GET"
                                    },
                                    {
                                        "href": "https://api.sandbox.paypal.com/v2/payments/captures/22A4162004478570J/refund",
                                        "rel": "refund",
                                        "method": "POST"
                                    },
                                    {
                                        "href": "https://api.sandbox.paypal.com/v2/checkout/orders/806440346Y391300T",
                                        "rel": "up",
                                        "method": "GET"
                                    }
                                ],
                                "create_time": "2022-04-28T12:00:22Z",
                                "update_time": "2022-04-28T12:00:22Z"
                            }
                        ]
                    }
                }
            ],
            "payer": {
                "name": {
                    "given_name": "test",
                    "surname": "buyer"
                },
                "email_address": "dummy@dummy.dummy",
                "payer_id": "Q739JNKWH67HE",
                "address": {
                    "country_code": "DE"
                }
            },
            "links": [
                {
                    "href": "https://api.sandbox.paypal.com/v2/checkout/orders/806440346Y391300T",
                    "rel": "self",
                    "method": "GET"
                }
            ]
        })
    )
    return event, o1


def get_test_order():
    return {'id': '806440346Y391300T',
            'intent': 'CAPTURE',
            'status': 'COMPLETED',
            'purchase_units': [{'reference_id': 'default',
                                'amount': {'currency_code': 'EUR', 'value': '43.59'},
                                'payee': {'email_address': 'dummy-facilitator@dummy.dummy',
                                          'merchant_id': 'G6R2B9YXADKWW'},
                                'description': 'Order JWJGC for PayPal v2',
                                'custom_id': 'Order PAYPALV2-JWJGC',
                                'soft_descriptor': 'MARTINFACIL',
                                'payments': {'captures': [{'id': '22A4162004478570J',
                                                           'status': 'COMPLETED',
                                                           'amount': {'currency_code': 'EUR', 'value': '43.59'},
                                                           'final_capture': True,
                                                           'disbursement_mode': 'INSTANT',
                                                           'seller_protection': {'status': 'ELIGIBLE',
                                                                                 'dispute_categories': [
                                                                                     'ITEM_NOT_RECEIVED',
                                                                                     'UNAUTHORIZED_TRANSACTION']},
                                                           'seller_receivable_breakdown': {
                                                               'gross_amount': {'currency_code': 'EUR',
                                                                                'value': '43.59'},
                                                               'paypal_fee': {'currency_code': 'EUR', 'value': '1.18'},
                                                               'net_amount': {'currency_code': 'EUR',
                                                                              'value': '42.41'}},
                                                           'custom_id': 'Order PAYPALV2-JWJGC',
                                                           'links': [{
                                                               'href': 'https://api.sandbox.paypal.com/v2/payments/captures/22A4162004478570J',
                                                               'rel': 'self',
                                                               'method': 'GET'},
                                                               {
                                                                   'href': 'https://api.sandbox.paypal.com/v2/payments/captures/22A4162004478570J/refund',
                                                                   'rel': 'refund',
                                                                   'method': 'POST'},
                                                               {
                                                                   'href': 'https://api.sandbox.paypal.com/v2/checkout/orders/806440346Y391300T',
                                                                   'rel': 'up',
                                                                   'method': 'GET'}],
                                                           'create_time': '2022-04-28T12:00:22Z',
                                                           'update_time': '2022-04-28T12:00:22Z'}]}}],
            'payer': {'name': {'given_name': 'test', 'surname': 'buyer'},
                      'email_address': 'dummy@dummy.dummy',
                      'payer_id': 'Q739JNKWH67HE',
                      'address': {'country_code': 'DE'}},
            'create_time': '2022-04-28T11:59:59Z',
            'update_time': '2022-04-28T12:00:22Z',
            'links': [{'href': 'https://api.sandbox.paypal.com/v2/checkout/orders/806440346Y391300T',
                       'rel': 'self',
                       'method': 'GET'}]}


def get_test_refund():
    return {
        "id": "1YK122615V244890X",
        "amount": {
            "currency_code": "EUR",
            "value": "43.59"
        },
        "seller_payable_breakdown": {
            "gross_amount": {
                "currency_code": "EUR",
                "value": "43.59"
            },
            "paypal_fee": {
                "currency_code": "EUR",
                "value": "1.18"
            },
            "net_amount": {
                "currency_code": "EUR",
                "value": "42.41"
            },
            "total_refunded_amount": {
                "currency_code": "EUR",
                "value": "43.59"
            }
        },
        "custom_id": "Order PAYPALV2-JWJGC",
        "status": "COMPLETED",
        "create_time": "2022-04-28T07:50:56-07:00",
        "update_time": "2022-04-28T07:50:56-07:00",
        "links": [
            {
                "href": "https://api.sandbox.paypal.com/v2/payments/refunds/1YK122615V244890X",
                "rel": "self",
                "method": "GET"
            },
            {
                "href": "https://api.sandbox.paypal.com/v2/payments/captures/22A4162004478570J",
                "rel": "up",
                "method": "GET"
            }
        ]
    }


class Object():
    pass


def init_api(self):
    class Client():
        environment = Object()
        environment.client_id = '12345'
        environment.merchant_id = 'G6R2B9YXADKWW'

        def execute(self, request):
            response = Object()
            response.result = request
            return response

    self.client = Client()


@pytest.mark.django_db
def test_webhook_all_good(env, client, monkeypatch):
    order = env[1]
    pp_order = Result(get_test_order())
    monkeypatch.setattr("paypalcheckoutsdk.orders.OrdersGetRequest", lambda *args: pp_order)
    monkeypatch.setattr("pretix.plugins.paypal2.payment.PaypalMethod.init_api", init_api)

    with scopes_disabled():
        ReferencedPayPalObject.objects.create(order=order, payment=order.payments.first(),
                                              reference="806440346Y391300T")

    client.post('/_paypal/webhook/', json.dumps(
        {
            "id": "WH-4T867178D0574904F-7TT11736YU643990P",
            "create_time": "2022-04-28T12:00:37.077Z",
            "resource_type": "checkout-order",
            "event_type": "CHECKOUT.ORDER.COMPLETED",
            "summary": "Checkout Order Completed",
            "resource": {
                "update_time": "2022-04-28T12:00:22Z",
                "create_time": "2022-04-28T11:59:59Z",
                "purchase_units": [
                    {
                        "reference_id": "default",
                        "amount": {
                            "currency_code": "EUR",
                            "value": "43.59"
                        },
                        "payee": {
                            "email_address": "dummy-facilitator@dummy.dummy",
                            "merchant_id": "G6R2B9YXADKWW"
                        },
                        "description": "Order JWJGC for PayPal v2",
                        "custom_id": "Order PAYPALV2-JWJGC",
                        "soft_descriptor": "MARTINFACIL",
                        "payments": {
                            "captures": [
                                {
                                    "id": "22A4162004478570J",
                                    "status": "COMPLETED",
                                    "amount": {
                                        "currency_code": "EUR",
                                        "value": "43.59"
                                    },
                                    "final_capture": True,
                                    "disbursement_mode": "INSTANT",
                                    "seller_protection": {
                                        "status": "ELIGIBLE",
                                        "dispute_categories": [
                                            "ITEM_NOT_RECEIVED",
                                            "UNAUTHORIZED_TRANSACTION"
                                        ]
                                    },
                                    "seller_receivable_breakdown": {
                                        "gross_amount": {
                                            "currency_code": "EUR",
                                            "value": "43.59"
                                        },
                                        "paypal_fee": {
                                            "currency_code": "EUR",
                                            "value": "1.18"
                                        },
                                        "net_amount": {
                                            "currency_code": "EUR",
                                            "value": "42.41"
                                        }
                                    },
                                    "custom_id": "Order PAYPALV2-JWJGC",
                                    "links": [
                                        {
                                            "href": "https://api.sandbox.paypal.com/v2/payments/captures/22A4162004478570J",
                                            "rel": "self",
                                            "method": "GET"
                                        },
                                        {
                                            "href": "https://api.sandbox.paypal.com/v2/payments/captures/22A4162004478570J/refund",
                                            "rel": "refund",
                                            "method": "POST"
                                        },
                                        {
                                            "href": "https://api.sandbox.paypal.com/v2/checkout/orders/806440346Y391300T",
                                            "rel": "up",
                                            "method": "GET"
                                        }
                                    ],
                                    "create_time": "2022-04-28T12:00:22Z",
                                    "update_time": "2022-04-28T12:00:22Z"
                                }
                            ]
                        }
                    }
                ],
                "links": [
                    {
                        "href": "https://api.sandbox.paypal.com/v2/checkout/orders/806440346Y391300T",
                        "rel": "self",
                        "method": "GET"
                    }
                ],
                "id": "806440346Y391300T",
                "intent": "CAPTURE",
                "payer": {
                    "name": {
                        "given_name": "test",
                        "surname": "buyer"
                    },
                    "email_address": "dummy@dummy.dummy",
                    "payer_id": "Q739JNKWH67HE",
                    "address": {
                        "country_code": "DE"
                    }
                },
                "status": "COMPLETED"
            },
            "status": "SUCCESS",
            "links": [
                {
                    "href": "https://api.sandbox.paypal.com/v1/notifications/webhooks-events/WH-4T867178D0574904F-7TT11736YU643990P",
                    "rel": "self",
                    "method": "GET",
                    "encType": "application/json"
                },
                {
                    "href": "https://api.sandbox.paypal.com/v1/notifications/webhooks-events/WH-4T867178D0574904F-7TT11736YU643990P/resend",
                    "rel": "resend",
                    "method": "POST",
                    "encType": "application/json"
                }
            ],
            "event_version": "1.0",
            "resource_version": "2.0"
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
    with scopes_disabled():
        order.payments.update(state=OrderPayment.PAYMENT_STATE_PENDING)

    pp_order = Result(get_test_order())
    monkeypatch.setattr("paypalcheckoutsdk.orders.OrdersGetRequest", lambda *args: pp_order)
    monkeypatch.setattr("pretix.plugins.paypal2.payment.PaypalMethod.init_api", init_api)
    with scopes_disabled():
        ReferencedPayPalObject.objects.create(order=order, payment=order.payments.first(),
                                              reference="806440346Y391300T")

    client.post('/_paypal/webhook/', json.dumps(
        {
            "id": "WH-88L014580L300952M-4BX97184625330932",
            "create_time": "2022-04-28T12:00:26.840Z",
            "resource_type": "capture",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "summary": "Payment completed for EUR 43.59 EUR",
            "resource": {
                "disbursement_mode": "INSTANT",
                "amount": {
                    "value": "43.59",
                    "currency_code": "EUR"
                },
                "seller_protection": {
                    "dispute_categories": [
                        "ITEM_NOT_RECEIVED",
                        "UNAUTHORIZED_TRANSACTION"
                    ],
                    "status": "ELIGIBLE"
                },
                "supplementary_data": {
                    "related_ids": {
                        "order_id": "806440346Y391300T"
                    }
                },
                "update_time": "2022-04-28T12:00:22Z",
                "create_time": "2022-04-28T12:00:22Z",
                "final_capture": True,
                "seller_receivable_breakdown": {
                    "paypal_fee": {
                        "value": "1.18",
                        "currency_code": "EUR"
                    },
                    "gross_amount": {
                        "value": "43.59",
                        "currency_code": "EUR"
                    },
                    "net_amount": {
                        "value": "42.41",
                        "currency_code": "EUR"
                    }
                },
                "custom_id": "Order PAYPALV2-JWJGC",
                "links": [
                    {
                        "method": "GET",
                        "rel": "self",
                        "href": "https://api.sandbox.paypal.com/v2/payments/captures/22A4162004478570J"
                    },
                    {
                        "method": "POST",
                        "rel": "refund",
                        "href": "https://api.sandbox.paypal.com/v2/payments/captures/22A4162004478570J/refund"
                    },
                    {
                        "method": "GET",
                        "rel": "up",
                        "href": "https://api.sandbox.paypal.com/v2/checkout/orders/806440346Y391300T"
                    }
                ],
                "id": "22A4162004478570J",
                "status": "COMPLETED"
            },
            "status": "SUCCESS",
            "links": [
                {
                    "href": "https://api.sandbox.paypal.com/v1/notifications/webhooks-events/WH-88L014580L300952M-4BX97184625330932",
                    "rel": "self",
                    "method": "GET",
                    "encType": "application/json"
                },
                {
                    "href": "https://api.sandbox.paypal.com/v1/notifications/webhooks-events/WH-88L014580L300952M-4BX97184625330932/resend",
                    "rel": "resend",
                    "method": "POST",
                    "encType": "application/json"
                }
            ],
            "event_version": "1.0",
            "resource_version": "2.0"
        }
    ), content_type='application_json')

    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_webhook_refund1(env, client, monkeypatch):
    order = env[1]
    pp_order = Result(get_test_order())
    pp_refund = Result(get_test_refund())

    monkeypatch.setattr("paypalcheckoutsdk.orders.OrdersGetRequest", lambda *args: pp_order)
    monkeypatch.setattr("paypalcheckoutsdk.payments.RefundsGetRequest", lambda *args: pp_refund)
    monkeypatch.setattr("pretix.plugins.paypal2.payment.PaypalMethod.init_api", init_api)
    with scopes_disabled():
        ReferencedPayPalObject.objects.create(order=order, payment=order.payments.first(),
                                              reference="22A4162004478570J")

    client.post('/_paypal/webhook/', json.dumps(
        {
            "id": "WH-5LJ60612747357339-66248625WA926672S",
            "create_time": "2022-04-28T14:51:00.318Z",
            "resource_type": "refund",
            "event_type": "PAYMENT.CAPTURE.REFUNDED",
            "summary": "A EUR 43.59 EUR capture payment was refunded",
            "resource": {
                "seller_payable_breakdown": {
                    "total_refunded_amount": {
                        "value": "43.59",
                        "currency_code": "EUR"
                    },
                    "paypal_fee": {
                        "value": "1.18",
                        "currency_code": "EUR"
                    },
                    "gross_amount": {
                        "value": "42.41",
                        "currency_code": "EUR"
                    },
                    "net_amount": {
                        "value": "43.59",
                        "currency_code": "EUR"
                    }
                },
                "amount": {
                    "value": "43.59",
                    "currency_code": "EUR"
                },
                "update_time": "2022-04-28T07:50:56-07:00",
                "create_time": "2022-04-28T07:50:56-07:00",
                "custom_id": "Order PAYPALV2-JWJGC",
                "links": [
                    {
                        "method": "GET",
                        "rel": "self",
                        "href": "https://api.sandbox.paypal.com/v2/payments/refunds/1YK122615V244890X"
                    },
                    {
                        "method": "GET",
                        "rel": "up",
                        "href": "https://api.sandbox.paypal.com/v2/payments/captures/22A4162004478570J"
                    }
                ],
                "id": "1YK122615V244890X",
                "status": "COMPLETED"
            },
            "status": "SUCCESS",
            "links": [
                {
                    "href": "https://api.sandbox.paypal.com/v1/notifications/webhooks-events/WH-5LJ60612747357339-66248625WA926672S",
                    "rel": "self",
                    "method": "GET",
                    "encType": "application/json"
                },
                {
                    "href": "https://api.sandbox.paypal.com/v1/notifications/webhooks-events/WH-5LJ60612747357339-66248625WA926672S/resend",
                    "rel": "resend",
                    "method": "POST",
                    "encType": "application/json"
                }
            ],
            "event_version": "1.0",
            "resource_version": "2.0"
        }
    ), content_type='application_json')

    order = env[1]
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID

    with scopes_disabled():
        r = order.refunds.first()
        assert r.provider == 'paypal'
        assert r.amount == order.total
        assert r.payment == order.payments.first()
        assert r.state == OrderRefund.REFUND_STATE_EXTERNAL
        assert r.source == OrderRefund.REFUND_SOURCE_EXTERNAL


@pytest.mark.django_db
def test_webhook_refund2(env, client, monkeypatch):
    order = env[1]
    pp_order = Result(get_test_order())
    pp_refund = Result(get_test_refund())

    monkeypatch.setattr("paypalcheckoutsdk.orders.OrdersGetRequest", lambda *args: pp_order)
    monkeypatch.setattr("paypalcheckoutsdk.payments.RefundsGetRequest", lambda *args: pp_refund)
    monkeypatch.setattr("pretix.plugins.paypal2.payment.PaypalMethod.init_api", init_api)
    with scopes_disabled():
        ReferencedPayPalObject.objects.create(order=order, payment=order.payments.first(),
                                              reference="22A4162004478570J")

    client.post('/_paypal/webhook/', json.dumps(
        {
            "id": "WH-7FL378472F5218625-6WC87835CR8751809",
            "create_time": "2022-04-28T14:56:08.160Z",
            "resource_type": "refund",
            "event_type": "PAYMENT.CAPTURE.REFUNDED",
            "summary": "A EUR 43.59 EUR capture payment was refunded",
            "resource": {
                "seller_payable_breakdown": {
                    "total_refunded_amount": {
                        "value": "43.59",
                        "currency_code": "EUR"
                    },
                    "paypal_fee": {
                        "value": "01.18",
                        "currency_code": "EUR"
                    },
                    "gross_amount": {
                        "value": "43.59",
                        "currency_code": "EUR"
                    },
                    "net_amount": {
                        "value": "42.41",
                        "currency_code": "EUR"
                    }
                },
                "amount": {
                    "value": "43.59",
                    "currency_code": "EUR"
                },
                "update_time": "2022-04-28T07:56:04-07:00",
                "create_time": "2022-04-28T07:56:04-07:00",
                "custom_id": "Order PAYPALV2-JWJGC",
                "links": [
                    {
                        "method": "GET",
                        "rel": "self",
                        "href": "https://api.sandbox.paypal.com/v2/payments/refunds/3K87087190824201K"
                    },
                    {
                        "method": "GET",
                        "rel": "up",
                        "href": "https://api.sandbox.paypal.com/v2/payments/captures/22A4162004478570J"
                    }
                ],
                "id": "3K87087190824201K",
                "status": "COMPLETED"
            },
            "status": "SUCCESS",
            "links": [
                {
                    "href": "https://api.sandbox.paypal.com/v1/notifications/webhooks-events/WH-7FL378472F5218625-6WC87835CR8751809",
                    "rel": "self",
                    "method": "GET",
                    "encType": "application/json"
                },
                {
                    "href": "https://api.sandbox.paypal.com/v1/notifications/webhooks-events/WH-7FL378472F5218625-6WC87835CR8751809/resend",
                    "rel": "resend",
                    "method": "POST",
                    "encType": "application/json"
                }
            ],
            "event_version": "1.0",
            "resource_version": "2.0"
        }
    ), content_type='application_json')

    order = env[1]
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID

    with scopes_disabled():
        r = order.refunds.first()
        assert r.provider == 'paypal'
        assert r.amount == order.total
        assert r.payment == order.payments.first()
        assert r.state == OrderRefund.REFUND_STATE_EXTERNAL
        assert r.source == OrderRefund.REFUND_SOURCE_EXTERNAL
