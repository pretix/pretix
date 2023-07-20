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
import copy
import datetime
import json
from decimal import Decimal
from unittest import mock

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_countries.fields import Country
from django_scopes import scopes_disabled
from stripe.error import APIConnectionError
from tests.plugins.stripe.test_provider import MockedCharge

from pretix.base.models import InvoiceAddress, Order, OrderPosition
from pretix.base.models.orders import OrderFee, OrderPayment, OrderRefund


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def item2(event2):
    return event2.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def taxrule(event):
    return event.tax_rules.create(rate=Decimal('19.00'))


@pytest.fixture
def question(event, item):
    q = event.questions.create(question="T-Shirt size", type="S", identifier="ABC")
    q.items.add(item)
    q.options.create(answer="XL", identifier="LVETRWVU")
    return q


@pytest.fixture
def question2(event2, item2):
    q = event2.questions.create(question="T-Shirt size", type="S", identifier="ABC")
    q.items.add(item2)
    return q


@pytest.fixture
def quota(event, item):
    q = event.quotas.create(name="Budget Quota", size=200)
    q.items.add(item)
    return q


@pytest.fixture
def order(event, item, taxrule, question):
    testtime = datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)
    event.plugins += ",pretix.plugins.stripe"
    event.save()

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, secret="k24fiuwvu8kxz3y1",
            datetime=datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
            expires=datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=datetime.timezone.utc),
            total=23, locale='en'
        )
        p1 = o.payments.create(
            provider='stripe',
            state='refunded',
            amount=Decimal('23.00'),
            payment_date=testtime,
        )
        o.refunds.create(
            provider='stripe',
            state='done',
            source='admin',
            amount=Decimal('23.00'),
            execution_date=testtime,
            payment=p1,
        )
        o.payments.create(
            provider='banktransfer',
            state='pending',
            amount=Decimal('23.00'),
        )
        o.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.25'), tax_rate=Decimal('19.00'),
                      tax_value=Decimal('0.05'), tax_rule=taxrule)
        o.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.25'), tax_rate=Decimal('19.00'),
                      tax_value=Decimal('0.05'), tax_rule=taxrule, canceled=True)
        InvoiceAddress.objects.create(order=o, company="Sample company", country=Country('NZ'),
                                      vat_id="DE123", vat_id_validated=True, custom_field="Custom info")
        op = OrderPosition.objects.create(
            order=o,
            item=item,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={"full_name": "Peter", "_scheme": "full"},
            secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
            pseudonymization_id="ABCDEFGHKL",
            positionid=1,
        )
        OrderPosition.objects.create(
            order=o,
            item=item,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={"full_name": "Peter", "_scheme": "full"},
            secret="YBiYJrmF5ufiTLdV1iDf",
            pseudonymization_id="JKLM",
            canceled=True,
            positionid=2,
        )
        op.answers.create(question=question, answer='S')
        return o


@pytest.fixture
def clist_autocheckin(event):
    c = event.checkin_lists.create(name="Default", all_products=True, auto_checkin_sales_channels=['web'])
    return c


TEST_ORDERPOSITION_RES = {
    "id": 1,
    "order": "FOO",
    "positionid": 1,
    "item": 1,
    "variation": None,
    "price": "23.00",
    "attendee_name_parts": {"full_name": "Peter", "_scheme": "full"},
    "attendee_name": "Peter",
    "attendee_email": None,
    "voucher": None,
    "discount": None,
    "tax_rate": "0.00",
    "tax_value": "0.00",
    "tax_rule": None,
    "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
    "addon_to": None,
    "pseudonymization_id": "ABCDEFGHKL",
    "checkins": [],
    "downloads": [],
    "seat": None,
    "company": None,
    "street": None,
    "zipcode": None,
    "city": None,
    "country": None,
    "state": None,
    "valid_from": None,
    "valid_until": None,
    "blocked": None,
    "answers": [
        {
            "question": 1,
            "answer": "S",
            "question_identifier": "ABC",
            "options": [],
            "option_identifiers": []
        }
    ],
    "subevent": None,
    "canceled": False,
}
TEST_PAYMENTS_RES = [
    {
        "local_id": 1,
        "created": "2017-12-01T10:00:00Z",
        "payment_date": "2017-12-01T10:00:00Z",
        "provider": "stripe",
        "payment_url": None,
        "details": {
            "id": None,
            "payment_method": None
        },
        "state": "refunded",
        "amount": "23.00"
    },
    {
        "local_id": 2,
        "created": "2017-12-01T10:00:00Z",
        "payment_date": None,
        "provider": "banktransfer",
        "payment_url": None,
        "details": {},
        "state": "pending",
        "amount": "23.00"
    }
]
TEST_REFUNDS_RES = [
    {
        "local_id": 1,
        "payment": 1,
        "source": "admin",
        "created": "2017-12-01T10:00:00Z",
        "execution_date": "2017-12-01T10:00:00Z",
        "comment": None,
        "provider": "stripe",
        "details": {"id": None},
        "state": "done",
        "amount": "23.00"
    },
]
TEST_ORDER_RES = {
    "code": "FOO",
    "status": "n",
    "testmode": False,
    "secret": "k24fiuwvu8kxz3y1",
    "email": "dummy@dummy.test",
    "phone": None,
    "locale": "en",
    "customer": None,
    "datetime": "2017-12-01T10:00:00Z",
    "expires": "2017-12-10T10:00:00Z",
    "payment_date": "2017-12-01",
    "sales_channel": "web",
    "fees": [
        {
            "canceled": False,
            "fee_type": "payment",
            "value": "0.25",
            "description": "",
            "internal_type": "",
            "tax_rate": "19.00",
            "tax_value": "0.05"
        }
    ],
    "url": "http://example.com/dummy/dummy/order/FOO/k24fiuwvu8kxz3y1/",
    "payment_provider": "banktransfer",
    "total": "23.00",
    "comment": "",
    "custom_followup_at": None,
    "checkin_attention": False,
    "invoice_address": {
        "last_modified": "2017-12-01T10:00:00Z",
        "is_business": False,
        "company": "Sample company",
        "name": "",
        "name_parts": {},
        "street": "",
        "zipcode": "",
        "city": "",
        "country": "NZ",
        "state": "",
        "internal_reference": "",
        "custom_field": "Custom info",
        "vat_id": "DE123",
        "vat_id_validated": True
    },
    "require_approval": False,
    "valid_if_pending": False,
    "positions": [TEST_ORDERPOSITION_RES],
    "downloads": [],
    "payments": TEST_PAYMENTS_RES,
    "refunds": TEST_REFUNDS_RES,
}


@pytest.mark.django_db
def test_order_list_filter_subevent_date(token_client, organizer, event, order, item, taxrule, subevent, question):
    res = copy.deepcopy(TEST_ORDER_RES)
    with scopes_disabled():
        res["positions"][0]["id"] = order.positions.first().pk
        p = order.positions.first()
        p.subevent = subevent
        p.save()
        fee = order.fees.first()
    res["positions"][0]["item"] = item.pk
    res["positions"][0]["subevent"] = subevent.pk
    res["positions"][0]["answers"][0]["question"] = question.pk
    res["last_modified"] = order.last_modified.isoformat().replace('+00:00', 'Z')
    res["fees"][0]["tax_rule"] = taxrule.pk
    res["fees"][0]["id"] = fee.pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?subevent_after={}'.format(
        organizer.slug, event.slug,
        (subevent.date_from + datetime.timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
    ))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?subevent_after={}'.format(
        organizer.slug, event.slug,
        (subevent.date_from - datetime.timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
    ))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?subevent_before={}'.format(
        organizer.slug, event.slug,
        (subevent.date_from - datetime.timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
    ))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?subevent_before={}'.format(
        organizer.slug, event.slug,
        (subevent.date_from + datetime.timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
    ))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    # Test distinct-ness of results
    with scopes_disabled():
        OrderPosition.objects.create(
            order=order,
            item=item,
            variation=None,
            price=Decimal("23"),
            canceled=False,
            positionid=3,
            subevent=subevent,
        )
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orders/?subevent={}'.format(organizer.slug, event.slug, subevent.pk))
    assert len(resp.data['results']) == 1


@pytest.mark.django_db
def test_order_list(token_client, organizer, event, order, item, taxrule, question):
    res = dict(TEST_ORDER_RES)
    with scopes_disabled():
        res["positions"][0]["id"] = order.positions.first().pk
        res["fees"][0]["id"] = order.fees.first().pk
    res["positions"][0]["item"] = item.pk
    res["positions"][0]["answers"][0]["question"] = question.pk
    res["last_modified"] = order.last_modified.isoformat().replace('+00:00', 'Z')
    res["fees"][0]["tax_rule"] = taxrule.pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?code=FOO'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?code=BAR'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?testmode=false'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?testmode=true'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?status=n'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?status=p'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orders/?email=dummy@dummy.test'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orders/?email=foo@example.org'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?locale=en'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?locale=de'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?modified_since={}'.format(
        organizer.slug, event.slug,
        (order.last_modified - datetime.timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
    ))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?modified_since={}'.format(
        organizer.slug, event.slug, order.last_modified.isoformat().replace('+00:00', 'Z')
    ))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?modified_since={}'.format(
        organizer.slug, event.slug,
        (order.last_modified + datetime.timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
    ))
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?include_canceled_positions=false'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert len(resp.data['results'][0]['positions']) == 1

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?include_canceled_positions=true'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert len(resp.data['results'][0]['positions']) == 2

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?include_canceled_fees=false'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert len(resp.data['results'][0]['fees']) == 1

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?include_canceled_fees=true'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert len(resp.data['results'][0]['fees']) == 2


@pytest.mark.django_db
def test_order_detail(token_client, organizer, event, order, item, taxrule, question):
    res = dict(TEST_ORDER_RES)
    with scopes_disabled():
        res["positions"][0]["id"] = order.positions.first().pk
        res["fees"][0]["id"] = order.fees.first().pk
    res["positions"][0]["item"] = item.pk
    res["fees"][0]["tax_rule"] = taxrule.pk
    res["positions"][0]["answers"][0]["question"] = question.pk
    res["last_modified"] = order.last_modified.isoformat().replace('+00:00', 'Z')
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/'.format(organizer.slug, event.slug,
                                                                                order.code))
    assert resp.status_code == 200
    assert json.loads(json.dumps(res)) == json.loads(json.dumps(resp.data))

    order.status = 'p'
    order.save()
    event.settings.ticketoutput_pdf__enabled = True
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/'.format(organizer.slug, event.slug,
                                                                                order.code))
    assert len(resp.data['downloads']) == 1
    assert len(resp.data['positions'][0]['downloads']) == 1

    order.status = 'n'
    order.save()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/'.format(organizer.slug, event.slug,
                                                                                order.code))
    assert len(resp.data['downloads']) == 0
    assert len(resp.data['positions'][0]['downloads']) == 0

    event.settings.ticket_download_pending = True
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/'.format(organizer.slug, event.slug,
                                                                                order.code))
    assert len(resp.data['downloads']) == 1
    assert len(resp.data['positions'][0]['downloads']) == 1

    assert len(resp.data['positions']) == 1
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/?include_canceled_positions=true'.format(organizer.slug, event.slug, order.code))
    assert resp.status_code == 200
    assert len(resp.data['positions']) == 2

    assert len(resp.data['fees']) == 1
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/?include_canceled_fees=true'.format(organizer.slug, event.slug, order.code))
    assert resp.status_code == 200
    assert len(resp.data['fees']) == 2


@pytest.mark.django_db
def test_include_exclude_fields(token_client, organizer, event, order, item, taxrule, question):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/?exclude=positions.secret'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 200
    assert 'email' in resp.data
    assert 'url' in resp.data
    assert 'positions' in resp.data
    assert 'subevent' in resp.data['positions'][0]
    assert 'secret' not in resp.data['positions'][0]

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/?exclude=positions'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 200
    assert 'email' in resp.data
    assert 'url' in resp.data
    assert 'positions' not in resp.data

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/?exclude=email&exclude=url'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 200
    assert 'email' not in resp.data
    assert 'url' not in resp.data
    assert 'positions' in resp.data
    assert 'secret' in resp.data['positions'][0]

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/?include=email'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 200
    assert 'email' in resp.data
    assert 'url' not in resp.data
    assert 'positions' not in resp.data

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orders/{}/?include=email&include=positions&include=invoice_address.name&exclude=positions.secret'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert 'email' in resp.data
    assert 'url' not in resp.data
    assert 'positions' in resp.data
    assert 'subevent' in resp.data['positions'][0]
    assert 'secret' not in resp.data['positions'][0]
    assert 'city' not in resp.data['invoice_address']
    assert 'name' in resp.data['invoice_address']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/?include=email&include=positions.subevent'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 200
    assert 'email' in resp.data
    assert 'url' not in resp.data
    assert 'positions' in resp.data
    assert 'subevent' in resp.data['positions'][0]
    assert 'secret' not in resp.data['positions'][0]


@pytest.mark.django_db
def test_payment_list(token_client, organizer, event, order):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/payments/'.format(organizer.slug, event.slug,
                                                                                         order.code))
    assert resp.status_code == 200
    assert TEST_PAYMENTS_RES == resp.data['results']


@pytest.mark.django_db
def test_payment_detail(token_client, organizer, event, order):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/payments/1/'.format(organizer.slug, event.slug,
                                                                                           order.code))
    assert resp.status_code == 200
    assert TEST_PAYMENTS_RES[0] == resp.data


@pytest.mark.django_db
def test_payment_create_confirmed(token_client, organizer, event, order):
    djmail.outbox = []
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'provider': 'banktransfer',
        'state': 'confirmed',
        'amount': order.total,
        'send_email': False,
        'info': {
            'foo': 'bar'
        }
    })
    with scopes_disabled():
        p = order.payments.last()
    assert resp.status_code == 201
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    assert p.info_data == {'foo': 'bar'}
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_payment_create_pending(token_client, organizer, event, order):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'provider': 'banktransfer',
        'state': 'pending',
        'amount': order.total,
        'info': {
            'foo': 'bar'
        }
    })
    with scopes_disabled():
        p = order.payments.last()
    assert resp.status_code == 201
    assert p.state == OrderPayment.PAYMENT_STATE_PENDING
    assert p.info_data == {'foo': 'bar'}
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_payment_confirm(token_client, organizer, event, order):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/confirm/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'force': True})
    with scopes_disabled():
        p = order.payments.get(local_id=2)
    assert resp.status_code == 200
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    assert len(djmail.outbox) == 1

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/confirm/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'force': True})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_payment_confirm_no_email(token_client, organizer, event, order):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/confirm/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'force': True, 'send_email': False})
    with scopes_disabled():
        p = order.payments.get(local_id=2)
    assert resp.status_code == 200
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_payment_cancel(token_client, organizer, event, order):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/cancel/'.format(
        organizer.slug, event.slug, order.code
    ))
    with scopes_disabled():
        p = order.payments.get(local_id=2)
    assert resp.status_code == 200
    assert p.state == OrderPayment.PAYMENT_STATE_CANCELED

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/cancel/'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 400


@pytest.mark.django_db
def test_payment_refund_fail(token_client, organizer, event, order, monkeypatch):
    with scopes_disabled():
        order.payments.last().confirm()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'amount': '25.00',
        'mark_canceled': False
    })
    assert resp.status_code == 400
    assert resp.data == {'amount': ['Invalid refund amount, only 23.00 are available to refund.']}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'amount': '20.00',
        'mark_canceled': False
    })
    assert resp.status_code == 400
    assert resp.data == {'amount': ['Partial refund not available for this payment method.']}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'mark_canceled': False
    })
    assert resp.status_code == 400
    assert resp.data == {'amount': ['Full refund not available for this payment method.']}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'amount': '23.00',
        'mark_canceled': False
    })
    assert resp.status_code == 400
    assert resp.data == {'amount': ['Full refund not available for this payment method.']}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/1/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'amount': '23.00',
        'mark_canceled': False
    })
    assert resp.status_code == 400
    assert resp.data == {'detail': 'Invalid state of payment.'}


@pytest.mark.django_db
def test_payment_refund_success(token_client, organizer, event, order, monkeypatch):
    def charge_retr(*args, **kwargs):
        def refund_create(amount):
            r = MockedCharge()
            r.id = 'foo'
            r.status = 'succeeded'
            return r

        c = MockedCharge()
        c.refunds.create = refund_create
        return c

    with scopes_disabled():
        p1 = order.payments.create(
            provider='stripe',
            state='confirmed',
            amount=Decimal('23.00'),
            payment_date=order.datetime,
            info=json.dumps({
                'id': 'ch_123345345'
            })
        )
    monkeypatch.setattr("stripe.Charge.retrieve", charge_retr)
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/{}/refund/'.format(
        organizer.slug, event.slug, order.code, p1.local_id
    ), format='json', data={
        'amount': '23.00',
        'mark_canceled': False,
    })
    assert resp.status_code == 200
    with scopes_disabled():
        r = order.refunds.get(local_id=resp.data['local_id'])
        assert r.provider == "stripe"
        assert r.state == OrderRefund.REFUND_STATE_DONE
        assert r.source == OrderRefund.REFUND_SOURCE_ADMIN


@pytest.mark.django_db
def test_payment_refund_unavailable(token_client, organizer, event, order, monkeypatch):
    def charge_retr(*args, **kwargs):
        def refund_create(amount):
            raise APIConnectionError(message='Foo')

        c = MockedCharge()
        c.refunds.create = refund_create
        return c

    with scopes_disabled():
        p1 = order.payments.create(
            provider='stripe',
            state='confirmed',
            amount=Decimal('23.00'),
            payment_date=order.datetime,
            info=json.dumps({
                'id': 'ch_123345345'
            })
        )
    monkeypatch.setattr("stripe.Charge.retrieve", charge_retr)
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/{}/refund/'.format(
        organizer.slug, event.slug, order.code, p1.local_id
    ), format='json', data={
        'amount': '23.00',
        'mark_canceled': False,
    })
    assert resp.status_code == 400
    assert resp.data == {'detail': 'External error: We had trouble communicating with Stripe. Please try again and contact support if the problem persists.'}
    with scopes_disabled():
        r = order.refunds.last()
    assert r.provider == "stripe"
    assert r.state == OrderRefund.REFUND_STATE_FAILED
    assert r.source == OrderRefund.REFUND_SOURCE_ADMIN


@pytest.mark.django_db
def test_refund_list(token_client, organizer, event, order):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(organizer.slug, event.slug,
                                                                                        order.code))
    assert resp.status_code == 200
    assert TEST_REFUNDS_RES == resp.data['results']


@pytest.mark.django_db
def test_refund_detail(token_client, organizer, event, order):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/'.format(organizer.slug, event.slug,
                                                                                          order.code))
    assert resp.status_code == 200
    assert TEST_REFUNDS_RES[0] == resp.data


@pytest.mark.django_db
def test_refund_done(token_client, organizer, event, order):
    with scopes_disabled():
        r = order.refunds.get(local_id=1)
    r.state = 'transit'
    r.save()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/done/'.format(
        organizer.slug, event.slug, order.code
    ))
    with scopes_disabled():
        r = order.refunds.get(local_id=1)
    assert resp.status_code == 200
    assert r.state == OrderRefund.REFUND_STATE_DONE

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/done/'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 400


@pytest.mark.django_db
def test_refund_process_mark_refunded(token_client, organizer, event, order):
    with scopes_disabled():
        p = order.payments.get(local_id=1)
        p.create_external_refund()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/2/process/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'mark_canceled': True})
    with scopes_disabled():
        r = order.refunds.get(local_id=1)
    assert resp.status_code == 200
    assert r.state == OrderRefund.REFUND_STATE_DONE
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELED

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/2/process/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'mark_canceled': True})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_refund_process_mark_pending(token_client, organizer, event, order):
    with scopes_disabled():
        p = order.payments.get(local_id=1)
        p.create_external_refund()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/2/process/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'mark_canceled': False})
    with scopes_disabled():
        r = order.refunds.get(local_id=1)
    assert resp.status_code == 200
    assert r.state == OrderRefund.REFUND_STATE_DONE
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_refund_cancel(token_client, organizer, event, order):
    with scopes_disabled():
        r = order.refunds.get(local_id=1)
    r.state = 'transit'
    r.save()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/cancel/'.format(
        organizer.slug, event.slug, order.code
    ))
    with scopes_disabled():
        r = order.refunds.get(local_id=1)
    assert resp.status_code == 200
    assert r.state == OrderRefund.REFUND_STATE_CANCELED

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/cancel/'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 400


@pytest.mark.django_db
def test_orderposition_list(token_client, organizer, event, order, item, subevent, subevent2, question):
    i2 = copy.copy(item)
    i2.pk = None
    i2.save()
    with scopes_disabled():
        var = item.variations.create(value="Children")
        var2 = item.variations.create(value="Children")
        res = copy.copy(TEST_ORDERPOSITION_RES)
        op = order.positions.first()
    op.variation = var
    op.save()
    res["id"] = op.pk
    res["item"] = item.pk
    res["variation"] = var.pk
    res["answers"][0]["question"] = question.pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?order__status=n'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?order__status=p'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?item={}'.format(organizer.slug, event.slug, item.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?item__in={},{}'.format(
            organizer.slug, event.slug, item.pk, i2.pk
        ))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?item={}'.format(organizer.slug, event.slug, i2.pk))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?variation={}'.format(organizer.slug, event.slug, var.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?variation={}'.format(organizer.slug, event.slug, var2.pk))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?attendee_name=Peter'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?attendee_name=peter'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?attendee_name=Mark'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?secret=z3fsn8jyufm5kpk768q69gkbyr5f4h6w'.format(
            organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?secret=abc123'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?pseudonymization_id=ABCDEFGHKL'.format(
            organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?pseudonymization_id=FOO'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?search=FO'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?search=z3fsn8j'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?search=Peter'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?search=5f4h6w'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?order=FOO'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?order=BAR'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?has_checkin=false'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?has_checkin=true'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    with scopes_disabled():
        cl = event.checkin_lists.create(name="Default")
        c = op.checkins.create(datetime=datetime.datetime(2017, 12, 26, 10, 0, 0, tzinfo=datetime.timezone.utc), list=cl)
        op.checkins.create(datetime=datetime.datetime(2017, 12, 26, 10, 0, 0, tzinfo=datetime.timezone.utc), list=cl, successful=False)
    res['checkins'] = [{  # successful only
        'id': c.pk,
        'datetime': '2017-12-26T10:00:00Z',
        'list': cl.pk,
        'auto_checked_in': False,
        'device': None,
        'gate': None,
        'type': 'entry'
    }]
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?has_checkin=true'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']

    op.subevent = subevent
    op.save()
    res['subevent'] = subevent.pk

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?subevent={}'.format(organizer.slug, event.slug, subevent.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?subevent__in={},{}'.format(organizer.slug, event.slug,
                                                                                    subevent.pk, subevent2.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?subevent={}'.format(organizer.slug, event.slug,
                                                                             subevent.pk + 1))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?include_canceled_positions=false'.format(organizer.slug, event.slug))
    assert len(resp.data['results']) == 1
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?include_canceled_positions=true'.format(organizer.slug, event.slug))
    assert len(resp.data['results']) == 2


@pytest.mark.django_db
def test_orderposition_detail(token_client, organizer, event, order, item, question):
    res = dict(TEST_ORDERPOSITION_RES)
    with scopes_disabled():
        op = order.positions.first()
    res["id"] = op.pk
    res["item"] = item.pk
    res["answers"][0]["question"] = question.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(organizer.slug, event.slug,
                                                                                        op.pk))
    assert resp.status_code == 200
    assert res == resp.data

    order.status = 'p'
    order.save()
    event.settings.ticketoutput_pdf__enabled = True
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(organizer.slug, event.slug,
                                                                                        op.pk))
    assert len(resp.data['downloads']) == 1


@pytest.mark.django_db
def test_orderposition_detail_canceled(token_client, organizer, event, order, item, question):
    with scopes_disabled():
        op = order.all_positions.filter(canceled=True).first()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(organizer.slug, event.slug,
                                                                                        op.pk))
    assert resp.status_code == 404
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/{}/?include_canceled_positions=true'.format(
        organizer.slug, event.slug, op.pk))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_orderposition_delete(token_client, organizer, event, order, item, question):
    with scopes_disabled():
        op = order.positions.first()
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
        organizer.slug, event.slug, op.pk
    ))
    assert resp.status_code == 400
    assert resp.data == ['This operation would leave the order empty. Please cancel the order itself instead.']

    with scopes_disabled():
        op2 = OrderPosition.objects.create(
            order=order,
            item=item,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={"full_name": "Peter", "_scheme": "full"},
            secret="foobar",
            pseudonymization_id="BAZ",
        )
        order.refresh_from_db()
        order.total = Decimal('46')
        order.save()
        assert order.positions.count() == 2

    resp = token_client.delete('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
        organizer.slug, event.slug, op2.pk
    ))
    assert resp.status_code == 204
    with scopes_disabled():
        assert order.positions.count() == 1
        assert order.all_positions.count() == 3
    order.refresh_from_db()
    assert order.total == Decimal('23.25')


@pytest.mark.django_db
def test_order_mark_paid_pending(token_client, organizer, event, order):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_paid/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert len(djmail.outbox) == 1
    assert resp.data['status'] == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_mark_paid_canceled(token_client, organizer, event, order):
    order.status = Order.STATUS_CANCELED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_paid/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_order_mark_paid_expired_quota_free(token_client, organizer, event, order, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    with scopes_disabled():
        order.create_transactions()
        assert order.transactions.count() == 0
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_paid/'.format(
            organizer.slug, event.slug, order.code
        ),
        format='json',
        data={
            'send_email': False
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert len(djmail.outbox) == 0
    assert order.status == Order.STATUS_PAID
    with scopes_disabled():
        assert order.transactions.count() == 2


@pytest.mark.django_db
def test_order_mark_paid_expired_quota_fill(token_client, organizer, event, order, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    quota.size = 0
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_paid/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_mark_paid_locked(token_client, organizer, event, order):
    order.status = Order.STATUS_EXPIRED
    order.save()
    with event.lock():
        resp = token_client.post(
            '/api/v1/organizers/{}/events/{}/orders/{}/mark_paid/'.format(
                organizer.slug, event.slug, order.code
            )
        )
        assert resp.status_code == 409
        order.refresh_from_db()
        assert order.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_reactivate(token_client, organizer, event, order, quota):
    order.status = Order.STATUS_CANCELED
    order.save()
    with scopes_disabled():
        order.create_transactions()
        assert order.transactions.count() == 0
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/reactivate/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_PENDING
    with scopes_disabled():
        assert order.transactions.count() == 2


@pytest.mark.django_db
def test_order_reactivate_invalid(token_client, organizer, event, order):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/reactivate/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_order_mark_canceled_pending(token_client, organizer, event, order):
    with scopes_disabled():
        order.create_transactions()
        assert order.transactions.count() == 2
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_canceled/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_CANCELED
    assert len(djmail.outbox) == 1
    with scopes_disabled():
        assert order.transactions.count() == 4


@pytest.mark.django_db
def test_order_mark_canceled_pending_fee_not_allowed(token_client, organizer, event, order):
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_canceled/'.format(
            organizer.slug, event.slug, order.code
        ), data={
            'cancellation_fee': '700.00'
        }
    )
    assert resp.status_code == 400
    assert resp.data == {'detail': 'The cancellation fee cannot be higher than the total amount of this order.'}
    assert len(djmail.outbox) == 0

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_canceled/'.format(
            organizer.slug, event.slug, order.code
        ), data={
            'cancellation_fee': '7.00'
        }
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_PENDING
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_order_mark_canceled_pending_no_email(token_client, organizer, event, order):
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_canceled/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'send_email': False
        }
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_CANCELED
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_order_mark_canceled_expired(token_client, organizer, event, order):
    order.status = Order.STATUS_EXPIRED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_canceled/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_order_mark_paid_canceled_keep_fee(token_client, organizer, event, order):
    order.status = Order.STATUS_PAID
    order.save()
    with scopes_disabled():
        order.create_transactions()
        assert order.transactions.count() == 2
    with scopes_disabled():
        order.payments.create(state=OrderPayment.PAYMENT_STATE_CONFIRMED, amount=order.total)
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_canceled/'.format(
            organizer.slug, event.slug, order.code
        ), data={
            'cancellation_fee': '6.00'
        }
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_PAID
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID
    assert order.total == Decimal('6.00')
    with scopes_disabled():
        assert order.transactions.count() == 4


@pytest.mark.django_db
def test_order_mark_paid_refunded(token_client, organizer, event, order):
    order.status = Order.STATUS_PAID
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_refunded/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_order_mark_canceled_refunded(token_client, organizer, event, order):
    order.status = Order.STATUS_CANCELED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_refunded/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_order_mark_paid_unpaid(token_client, organizer, event, order):
    order.status = Order.STATUS_PAID
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_pending/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_PENDING


@pytest.mark.django_db
def test_order_mark_canceled_unpaid(token_client, organizer, event, order):
    order.status = Order.STATUS_CANCELED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_pending/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_order_mark_pending_expired(token_client, organizer, event, order):
    order.status = Order.STATUS_PENDING
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_expired/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_mark_paid_expired(token_client, organizer, event, order):
    order.status = Order.STATUS_PAID
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_expired/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_extend_paid(token_client, organizer, event, order):
    order.status = Order.STATUS_PAID
    order.save()
    newdate = (now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/extend/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'expires': newdate
        }
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_extend_pending(token_client, organizer, event, order):
    order.status = Order.STATUS_PENDING
    order.save()
    newdate = (now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/extend/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'expires': newdate
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING
    assert order.expires.astimezone(event.timezone).strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


@pytest.mark.django_db
def test_order_extend_expired_quota_empty(token_client, organizer, event, order, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    quota.size = 0
    quota.save()
    newdate = (now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/extend/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'expires': newdate
        }
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_extend_expired_quota_ignore(token_client, organizer, event, order, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    quota.size = 0
    quota.save()
    newdate = (now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/extend/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'expires': newdate,
            'force': True
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING
    assert order.expires.astimezone(event.timezone).strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


@pytest.mark.django_db
def test_order_extend_expired_quota_waiting_list(token_client, organizer, event, order, item, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    quota.size = 1
    quota.save()
    with scopes_disabled():
        event.waitinglistentries.create(item=item, email='foo@bar.com')
    newdate = (now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/extend/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'expires': newdate,
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING
    assert order.expires.astimezone(event.timezone).strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


@pytest.mark.django_db
def test_order_extend_expired_quota_left(token_client, organizer, event, order, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    quota.size = 2
    quota.save()
    with scopes_disabled():
        order.create_transactions()
        assert order.transactions.count() == 0
    newdate = (now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/extend/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'expires': newdate,
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING
    assert order.expires.astimezone(event.timezone).strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"
    with scopes_disabled():
        assert order.transactions.count() == 2


@pytest.mark.django_db
def test_order_pending_approve(token_client, organizer, event, order):
    order.require_approval = True
    order.save()
    with scopes_disabled():
        order.create_transactions()
        assert order.transactions.count() == 0
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/approve/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_PENDING
    assert not resp.data['require_approval']
    with scopes_disabled():
        assert order.transactions.count() == 2


@pytest.mark.django_db
def test_order_invalid_state_approve(token_client, organizer, event, order):
    order.require_approval = True
    order.status = Order.STATUS_CANCELED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/approve/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400

    order.require_approval = False
    order.status = Order.STATUS_PENDING
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/approve/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_order_pending_deny(token_client, organizer, event, order):
    order.require_approval = True
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/deny/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_CANCELED
    assert resp.data['require_approval']


@pytest.mark.django_db
def test_order_invalid_state_deny(token_client, organizer, event, order):
    order.require_approval = True
    order.status = Order.STATUS_CANCELED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/deny/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400

    order.require_approval = False
    order.status = Order.STATUS_PENDING
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/deny/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400


REFUND_CREATE_PAYLOAD = {
    "state": "created",
    "provider": "manual",
    "amount": "23.00",
    "source": "admin",
    "payment": 2,
    "info": {
        "foo": "bar",
    }
}


@pytest.mark.django_db
def test_refund_create(token_client, organizer, event, order):
    res = copy.deepcopy(REFUND_CREATE_PAYLOAD)
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        r = order.refunds.get(local_id=resp.data['local_id'])
    assert r.provider == "manual"
    assert r.amount == Decimal("23.00")
    assert r.state == "created"
    assert r.source == "admin"
    assert r.info_data == {"foo": "bar"}
    assert r.payment.local_id == 2
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_refund_create_mark_refunded(token_client, organizer, event, order):
    res = copy.deepcopy(REFUND_CREATE_PAYLOAD)
    res['mark_canceled'] = True
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        r = order.refunds.get(local_id=resp.data['local_id'])
    assert r.provider == "manual"
    assert r.amount == Decimal("23.00")
    assert r.state == "created"
    assert r.source == "admin"
    assert r.info_data == {"foo": "bar"}
    assert r.payment.local_id == 2
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_refund_create_webhook_sent(token_client, organizer, event, order):
    res = copy.deepcopy(REFUND_CREATE_PAYLOAD)
    res['state'] = "done"
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        r = order.refunds.get(local_id=resp.data['local_id'])
    assert r.provider == "manual"
    assert r.amount == Decimal("23.00")
    assert r.state == "done"
    with scopes_disabled():
        assert order.all_logentries().get(action_type="pretix.event.order.refund.done")


@pytest.mark.django_db
def test_refund_optional_fields(token_client, organizer, event, order):
    res = copy.deepcopy(REFUND_CREATE_PAYLOAD)
    del res['info']
    del res['payment']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        r = order.refunds.get(local_id=resp.data['local_id'])
    assert r.provider == "manual"
    assert r.amount == Decimal("23.00")
    assert r.state == "created"
    assert r.source == "admin"

    del res['state']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data=res
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_refund_create_invalid_payment(token_client, organizer, event, order):
    res = copy.deepcopy(REFUND_CREATE_PAYLOAD)
    res['payment'] = 7
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data=res
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_order_delete(token_client, organizer, event, order):
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_order_delete_test_mode(token_client, organizer, event, order):
    order.testmode = True
    order.save()
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert not Order.objects.filter(code=order.code).exists()


@pytest.mark.django_db
def test_order_delete_test_mode_voucher(token_client, organizer, event, order, item):
    order.testmode = True
    order.save()
    with scopes_disabled():
        q = event.quotas.create(name="Quota")
        q.items.add(item)
        voucher = event.vouchers.create(price_mode="set", value=15, quota=q, redeemed=1)
        op = order.positions.first()
        op.voucher = voucher
        op.save()

    assert voucher.redeemed == 1

    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert not Order.objects.filter(code=order.code).exists()
    voucher.refresh_from_db()
    assert voucher.redeemed == 0


@pytest.mark.django_db
def test_order_delete_test_mode_voucher_cancelled_position(token_client, organizer, event, order, item):
    order.testmode = True
    order.save()
    with scopes_disabled():
        q = event.quotas.create(name="Quota")
        q.items.add(item)
        voucher = event.vouchers.create(price_mode="set", value=15, quota=q, redeemed=42)
        op = order.all_positions.last()
        op.voucher = voucher
        op.save()

    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert not Order.objects.filter(code=order.code).exists()
    voucher.refresh_from_db()
    assert voucher.redeemed == 42


@pytest.mark.django_db
def test_order_delete_test_mode_voucher_cancelled_order(token_client, organizer, event, order, item):
    with scopes_disabled():
        order.testmode = True
        order.status = Order.STATUS_CANCELED
        order.save()
        q = event.quotas.create(name="Quota")
        q.items.add(item)
        voucher = event.vouchers.create(price_mode="set", value=15, quota=q, redeemed=42)
        op = order.positions.first()
        op.voucher = voucher
        op.save()

    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert not Order.objects.filter(code=order.code).exists()
    voucher.refresh_from_db()
    assert voucher.redeemed == 42


@pytest.mark.django_db
def test_revoked_secret_list(token_client, organizer, event):
    r = event.revoked_secrets.create(secret="abcd")
    res = {
        "id": r.id,
        "secret": "abcd",
        "created": r.created.isoformat().replace("+00:00", "Z")
    }
    resp = token_client.get('/api/v1/organizers/{}/events/{}/revokedsecrets/'.format(
        organizer.slug, event.slug,
    ))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_blocked_secret_list(token_client, organizer, event):
    r = event.blocked_secrets.create(secret="abcd", blocked=True)
    res = {
        "id": r.id,
        "secret": "abcd",
        "blocked": True,
        "updated": r.updated.isoformat().replace("+00:00", "Z")
    }
    resp = token_client.get('/api/v1/organizers/{}/events/{}/blockedsecrets/'.format(
        organizer.slug, event.slug,
    ))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_pdf_data(token_client, organizer, event, order, django_assert_max_num_queries):
    # order detail
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/?pdf_data=true'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 200
    assert resp.data['positions'][0].get('pdf_data')
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 200
    assert not resp.data['positions'][0].get('pdf_data')

    # order list
    with django_assert_max_num_queries(30):
        resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?pdf_data=true'.format(
            organizer.slug, event.slug
        ))
    assert resp.status_code == 200
    assert resp.data['results'][0]['positions'][0].get('pdf_data')
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/'.format(
        organizer.slug, event.slug
    ))
    assert resp.status_code == 200
    assert not resp.data['results'][0]['positions'][0].get('pdf_data')

    # position list
    with django_assert_max_num_queries(33):
        resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/?pdf_data=true'.format(
            organizer.slug, event.slug
        ))
    assert resp.status_code == 200
    assert resp.data['results'][0].get('pdf_data')
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/'.format(
        organizer.slug, event.slug
    ))
    assert resp.status_code == 200
    assert not resp.data['results'][0].get('pdf_data')

    posid = resp.data['results'][0]['id']

    # position detail
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/{}/?pdf_data=true'.format(
        organizer.slug, event.slug, posid
    ))
    assert resp.status_code == 200
    assert resp.data.get('pdf_data')
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
        organizer.slug, event.slug, posid
    ))
    assert resp.status_code == 200
    assert not resp.data.get('pdf_data')
