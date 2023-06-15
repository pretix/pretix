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
from django.core.files.base import ContentFile
from django.utils.timezone import now
from django_countries.fields import Country
from django_scopes import scopes_disabled
from tests.const import SAMPLE_PNG

from pretix.base.models import (
    InvoiceAddress, Item, Order, OrderPosition, Organizer, Question,
    SeatingPlan,
)
from pretix.base.models.orders import CartPosition, OrderFee, QuestionAnswer


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
def medium(organizer):
    return organizer.reusable_media.create(
        type="barcode",
        identifier="ABCDE"
    )


@pytest.fixture
def organizer2():
    return Organizer.objects.create(name='Partner', slug='partner')


@pytest.fixture
def medium2(organizer2):
    return organizer2.reusable_media.create(
        type="barcode",
        identifier="ABCDE"
    )


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
                                      vat_id="DE123", vat_id_validated=True)
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


ORDER_CREATE_PAYLOAD = {
    "email": "dummy@dummy.test",
    "phone": "+49622112345",
    "locale": "en",
    "sales_channel": "web",
    "valid_if_pending": True,
    "fees": [
        {
            "fee_type": "payment",
            "value": "0.25",
            "description": "",
            "internal_type": "",
            "tax_rule": None
        }
    ],
    "payment_provider": "banktransfer",
    "invoice_address": {
        "is_business": False,
        "company": "Sample company",
        "name_parts": {"full_name": "Fo"},
        "street": "Bar",
        "state": "",
        "zipcode": "",
        "city": "Sample City",
        "country": "NZ",
        "internal_reference": "",
        "custom_field": None,
        "vat_id": ""
    },
    "positions": [
        {
            "positionid": 1,
            "item": 1,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "company": "FOOCORP",
            "answers": [
                {
                    "question": 1,
                    "answer": "S",
                    "options": []
                }
            ],
            "subevent": None
        }
    ],
}


@pytest.mark.django_db
def test_order_create(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    with scopes_disabled():
        customer = organizer.customers.create()
    res['customer'] = customer.identifier
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert not resp.data['positions'][0].get('pdf_data')
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
    assert o.customer == customer
    assert o.email == "dummy@dummy.test"
    assert o.phone == "+49622112345"
    assert o.locale == "en"
    assert o.total == Decimal('23.25')
    assert o.status == Order.STATUS_PENDING
    assert o.sales_channel == "web"
    assert o.valid_if_pending
    assert not o.testmode

    with scopes_disabled():
        p = o.payments.first()
    assert p.provider == "banktransfer"
    assert p.amount == o.total
    assert p.state == "created"

    with scopes_disabled():
        fee = o.fees.first()
    assert fee.fee_type == "payment"
    assert fee.value == Decimal('0.25')
    ia = o.invoice_address
    assert ia.company == "Sample company"
    assert ia.name_parts == {"full_name": "Fo", "_scheme": "full"}
    assert ia.name_cached == "Fo"
    with scopes_disabled():
        assert o.positions.count() == 1
        pos = o.positions.first()
    assert pos.item == item
    assert pos.price == Decimal("23.00")
    assert pos.attendee_name_parts == {"full_name": "Peter", "_scheme": "full"}
    assert pos.company == "FOOCORP"
    with scopes_disabled():
        answ = pos.answers.first()
    assert answ.question == question
    assert answ.answer == "S"
    with scopes_disabled():
        assert o.transactions.count() == 2


@pytest.mark.django_db
def test_order_create_simulate(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    question.type = Question.TYPE_CHOICE_MULTIPLE
    question.save()
    with scopes_disabled():
        opt = question.options.create(answer="L")
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['answers'][0]['options'] = [opt.pk]
    res['simulate'] = True
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        assert Order.objects.count() == 0
        assert QuestionAnswer.objects.count() == 0
        assert OrderPosition.objects.count() == 0
        assert OrderFee.objects.count() == 0
        assert InvoiceAddress.objects.count() == 0
    d = resp.data
    del d['last_modified']
    del d['secret']
    del d['url']
    del d['expires']
    del d['invoice_address']['last_modified']
    del d['positions'][0]['secret']
    assert d == {
        'code': 'PREVIEW',
        'status': 'n',
        'testmode': False,
        'email': 'dummy@dummy.test',
        'phone': '+49622112345',
        'customer': None,
        'locale': 'en',
        'datetime': None,
        'payment_date': None,
        'payment_provider': None,
        'valid_if_pending': True,
        'fees': [
            {
                'id': 0,
                'fee_type': 'payment',
                'value': '0.25',
                'description': '',
                'internal_type': '',
                'tax_rate': '0.00',
                'tax_value': '0.00',
                'tax_rule': None,
                'canceled': False
            }
        ],
        'total': '23.25',
        'comment': '',
        "custom_followup_at": None,
        'invoice_address': {
            'is_business': False,
            'company': 'Sample company',
            'name': 'Fo',
            'name_parts': {'full_name': 'Fo', '_scheme': 'full'},
            'street': 'Bar',
            'zipcode': '',
            'city': 'Sample City',
            'country': 'NZ',
            'state': '',
            'vat_id': '',
            'vat_id_validated': False,
            'internal_reference': '',
            'custom_field': None
        },
        'positions': [
            {
                'id': 0,
                'order': '',
                'positionid': 1,
                'item': item.pk,
                'variation': None,
                'price': '23.00',
                'attendee_name': 'Peter',
                'attendee_name_parts': {'full_name': 'Peter', '_scheme': 'full'},
                'attendee_email': None,
                'voucher': None,
                'tax_rate': '0.00',
                'tax_value': '0.00',
                'addon_to': None,
                'subevent': None,
                'discount': None,
                'checkins': [],
                'downloads': [],
                "valid_from": None,
                "valid_until": None,
                "blocked": None,
                'answers': [
                    {'question': question.pk, 'answer': 'L', 'question_identifier': 'ABC',
                     'options': [opt.pk],
                     'option_identifiers': [opt.identifier]}
                ],
                'tax_rule': None,
                'pseudonymization_id': 'PREVIEW',
                'seat': None,
                'company': "FOOCORP",
                'street': None,
                'city': None,
                'zipcode': None,
                'state': None,
                'country': None,
                'canceled': False
            }
        ],
        'downloads': [],
        'checkin_attention': False,
        'payments': [],
        'refunds': [],
        'require_approval': False,
        'sales_channel': 'web',
    }


@pytest.mark.django_db
def test_order_create_positionids_addons_simulated(token_client, organizer, event, item, quota):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None
        },
        {
            "positionid": 2,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": 1,
            "answers": [],
            "subevent": None
        }
    ]
    res['simulate'] = True
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    del resp.data['positions'][0]['secret']
    del resp.data['positions'][1]['secret']
    assert [dict(f) for f in resp.data['positions']] == [
        {'id': 0, 'order': '', 'positionid': 1, 'item': item.pk, 'variation': None, 'price': '23.00',
         'attendee_name': 'Peter', 'attendee_name_parts': {'full_name': 'Peter', '_scheme': 'full'}, 'company': None,
         'street': None, 'zipcode': None, 'city': None, 'country': None, 'state': None, 'attendee_email': None,
         'voucher': None, 'tax_rate': '0.00', 'tax_value': '0.00', 'discount': None,
         'addon_to': None, 'subevent': None, 'checkins': [], 'downloads': [], 'answers': [], 'tax_rule': None,
         'pseudonymization_id': 'PREVIEW', 'seat': None, 'canceled': False, 'valid_from': None, 'valid_until': None, 'blocked': None},
        {'id': 0, 'order': '', 'positionid': 2, 'item': item.pk, 'variation': None, 'price': '23.00',
         'attendee_name': 'Peter', 'attendee_name_parts': {'full_name': 'Peter', '_scheme': 'full'}, 'company': None,
         'street': None, 'zipcode': None, 'city': None, 'country': None, 'state': None, 'attendee_email': None,
         'voucher': None, 'tax_rate': '0.00', 'tax_value': '0.00', 'discount': None,
         'addon_to': 1, 'subevent': None, 'checkins': [], 'downloads': [], 'answers': [], 'tax_rule': None,
         'pseudonymization_id': 'PREVIEW', 'seat': None, 'canceled': False, 'valid_from': None, 'valid_until': None, 'blocked': None}
    ]


@pytest.mark.django_db
def test_order_create_autocheckin(token_client, organizer, event, item, quota, question, clist_autocheckin):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert "web" in clist_autocheckin.auto_checkin_sales_channels
        assert o.positions.first().checkins.first().auto_checked_in

    clist_autocheckin.auto_checkin_sales_channels = []
    clist_autocheckin.save()

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert clist_autocheckin.auto_checkin_sales_channels == []
        assert o.positions.first().checkins.count() == 0


@pytest.mark.django_db
def test_order_create_require_approval(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['require_approval'] = True
    res['send_email'] = True
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.require_approval
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Your order: {}".format(resp.data['code'])
    assert "approval" in djmail.outbox[0].body


@pytest.mark.django_db
def test_order_create_invoice_address_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['invoice_address']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        with pytest.raises(InvoiceAddress.DoesNotExist):
            o.invoice_address


@pytest.mark.django_db
def test_order_create_sales_channel_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['sales_channel']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
    assert o.sales_channel == "web"


@pytest.mark.django_db
def test_order_create_sales_channel_invalid(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['sales_channel'] = 'foo'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'sales_channel': ['Unknown sales channel.']}


@pytest.mark.django_db
def test_order_create_in_test_mode(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['testmode'] = True
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
    assert o.testmode


@pytest.mark.django_db
def test_order_create_in_test_mode_saleschannel_limited(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['testmode'] = True
    res['sales_channel'] = 'baz'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'testmode': ['This sales channel does not provide support for test mode.']}


@pytest.mark.django_db
def test_order_create_attendee_name_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['attendee_name'] = None
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['attendee_name_parts']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.positions.first().attendee_name_parts == {}


@pytest.mark.django_db
def test_order_create_legacy_attendee_name(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['attendee_name'] = 'Peter'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    del res['positions'][0]['attendee_name_parts']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201

    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.positions.first().attendee_name_parts == {"_legacy": "Peter"}


@pytest.mark.django_db
def test_order_create_legacy_invoice_name(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['invoice_address']['name'] = 'Peter'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    del res['invoice_address']['name_parts']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.invoice_address.name_parts == {"_legacy": "Peter"}


@pytest.mark.django_db
def test_order_create_code_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['code'] = 'ABCDE'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
    assert o.code == "ABCDE"

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'code': ['This order code is already in use.']}

    res['code'] = 'ABaDE'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'code': ['This order code contains invalid characters.']}


@pytest.mark.django_db
def test_order_email_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['email']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
    assert not o.email


@pytest.mark.django_db
def test_order_create_payment_provider_optional_free(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['price'] = '0.00'
    res['positions'][0]['status'] = 'p'
    del res['payment_provider']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert not o.payments.exists()


@pytest.mark.django_db
def test_order_create_payment_info_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201

    res['payment_info'] = {
        'foo': {
            'bar': [1, 2],
            'test': False
        }
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])

        p = o.payments.first()
    assert p.provider == "banktransfer"
    assert p.amount == o.total
    assert json.loads(p.info) == res['payment_info']


@pytest.mark.django_db
def test_order_create_position_secret_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.positions.first().secret

    res['positions'][0]['secret'] = "aaa"
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.positions.first().secret == "aaa"

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400

    assert resp.data == {'positions': [{'secret': ['You cannot assign a position secret that already exists.']}]}


@pytest.mark.django_db
def test_order_create_tax_rules(token_client, organizer, event, item, quota, question, taxrule):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'][0]['tax_rule'] = taxrule.pk
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    item.tax_rule = taxrule
    item.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        fee = o.fees.first()
    assert fee.fee_type == "payment"
    assert fee.value == Decimal('0.25')
    assert fee.tax_rate == Decimal('19.00')
    assert fee.tax_rule == taxrule
    ia = o.invoice_address
    assert ia.company == "Sample company"
    with scopes_disabled():
        pos = o.positions.first()
    assert pos.item == item
    assert pos.tax_rate == Decimal('19.00')
    assert pos.tax_value == Decimal('3.67')
    assert pos.tax_rule == taxrule


@pytest.mark.django_db
def test_order_create_fee_type_validation(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'][0]['fee_type'] = 'unknown'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'fees': [{'fee_type': ['"unknown" is not a valid choice.']}]}


@pytest.mark.django_db
def test_order_create_fee_as_percentage(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'][0]['_treat_value_as_percentage'] = True
    res['fees'][0]['value'] = '10.00'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        fee = o.fees.first()
        assert fee.value == Decimal('2.30')
        assert o.total == Decimal('25.30')


@pytest.mark.django_db
def test_order_create_fee_with_auto_tax(token_client, organizer, event, item, quota, question, taxrule):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'][0]['_split_taxes_like_products'] = True
    res['fees'][0]['_treat_value_as_percentage'] = True
    res['fees'][0]['value'] = '10.00'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    item.tax_rule = taxrule
    item.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        fee = o.fees.first()
        assert fee.value == Decimal('2.30')
        assert fee.tax_rate == Decimal('19.00')
        assert o.total == Decimal('25.30')


@pytest.mark.django_db
def test_order_create_negative_fee_with_auto_tax(token_client, organizer, event, item, quota, question, taxrule):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'][0]['_split_taxes_like_products'] = True
    res['fees'][0]['value'] = '-10.00'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    item.tax_rule = taxrule
    item.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        fee = o.fees.first()
        assert fee.value == Decimal('-10.00')
        assert fee.tax_value == Decimal('-1.60')
        assert fee.tax_rate == Decimal('19.00')
        assert o.total == Decimal('13.00')


@pytest.mark.django_db
def test_order_create_tax_rule_wrong_event(token_client, organizer, event, item, quota, question, taxrule2):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'][0]['tax_rule'] = taxrule2.pk
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'fees': [{'tax_rule': ['The specified tax rate does not belong to this event.']}]}


@pytest.mark.django_db
def test_order_create_subevent_not_allowed(token_client, organizer, event, item, quota, question, subevent2):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['subevent'] = subevent2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'subevent': ['You cannot set a subevent for this event.']}]}


@pytest.mark.django_db
def test_order_create_empty(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'] = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': ['An order cannot be empty.']}


@pytest.mark.django_db
def test_order_create_subevent_validation(token_client, organizer, event, item, subevent, subevent2, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'subevent': ['You need to set a subevent.']}]}

    res['positions'][0]['subevent'] = subevent2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'subevent': ['The specified subevent does not belong to this event.']}]}


@pytest.mark.django_db
def test_order_create_item_validation(token_client, organizer, event, item, item2, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    item.active = False
    item.save()
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'item': ['The specified item is not active.']}]}
    item.active = True
    item.save()

    res['positions'][0]['item'] = item2.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'item': ['The specified item does not belong to this event.']}]}

    with scopes_disabled():
        var2 = item2.variations.create(value="A")
        quota.variations.add(var2)

    res['positions'][0]['item'] = item.pk
    res['positions'][0]['variation'] = var2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'variation': ['You cannot specify a variation for this item.']}]}

    with scopes_disabled():
        var1 = item.variations.create(value="A")
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['variation'] = var1.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'item': ['The product "Budget Ticket" is not assigned to a quota.']}]}

    with scopes_disabled():
        quota.variations.add(var1)
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201

    res['positions'][0]['variation'] = var2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [{'variation': ['The specified variation does not belong to the specified item.']}]}

    res['positions'][0]['variation'] = None
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'variation': ['You should specify a variation for this item.']}]}


@pytest.mark.django_db
def test_order_create_subevent_disabled(token_client, organizer, event, item, subevent, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['subevent'] = subevent.pk
    s = item.subeventitem_set.create(subevent=subevent, disabled=True)
    quota.subevent = subevent
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'item': ['The product "Budget Ticket" is not available on this date.']}]}

    s.delete()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_order_create_subevent_variation_disabled(token_client, organizer, event, item, subevent, quota, question):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        var = item2.variations.create(default_price=12, value="XS")
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item2.pk
    res['positions'][0]['variation'] = var.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['subevent'] = subevent.pk
    s = var.subeventitemvariation_set.create(subevent=subevent, disabled=True)
    quota.subevent = subevent
    quota.items.add(item2)
    quota.variations.add(var)
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'item': ['The product "Budget Ticket" is not available on this date.']}]}

    s.delete()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_order_create_positionids_addons(token_client, organizer, event, item, quota):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None
        },
        {
            "positionid": 2,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": 1,
            "answers": [],
            "subevent": None
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        pos1 = o.positions.first()
        pos2 = o.positions.last()
    assert pos2.addon_to == pos1


@pytest.mark.django_db
def test_order_create_is_bundled_addons(token_client, organizer, event, item, quota):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None
        },
        {
            "positionid": 2,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": 1,
            "is_bundled": True,
            "answers": [],
            "subevent": None
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        pos1 = o.positions.first()
        pos2 = o.positions.last()
    assert pos2.addon_to == pos1
    assert pos2.is_bundled


@pytest.mark.django_db
def test_order_create_positionid_validation(token_client, organizer, event, item, quota):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None
        },
        {
            "positionid": 2,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": 2,
            "answers": [],
            "subevent": None
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {},
            {
                'addon_to': [
                    'If you set addon_to, you need to make sure that the '
                    'referenced position ID exists and is transmitted directly '
                    'before its add-ons.'
                ]
            }
        ]
    }

    res['positions'] = [
        {
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None
        },
        {
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": 2,
            "answers": [],
            "subevent": None
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [
        {'positionid': ["If you set addon_to on any position, you need to specify position IDs manually."]},
        {'positionid': ["If you set addon_to on any position, you need to specify position IDs manually."]}
    ]}

    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "answers": [],
            "subevent": None
        },
        {
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "answers": [],
            "subevent": None
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {},
            {
                'positionid': ['If you set position IDs manually, you need to do so for all positions.']
            }
        ]
    }

    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "answers": [],
            "subevent": None
        },
        {
            "positionid": 3,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "answers": [],
            "subevent": None
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {},
            {
                'positionid': ['Position IDs need to be consecutive.']
            }
        ]
    }

    res['positions'] = [
        {
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "answers": [],
            "subevent": None
        },
        {
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "answers": [],
            "subevent": None
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.positions.first().positionid == 1
        assert o.positions.last().positionid == 2


@pytest.mark.django_db
def test_order_create_answer_validation(token_client, organizer, event, item, quota, question, question2):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [{'answers': [{'question': ['The specified question does not belong to this event.']}]}]}

    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['answers'][0]['options'] = [question.options.first().pk]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'answers': [
        {'non_field_errors': ['You should not specify options if the question is not of a choice type.']}]}]}

    question.type = Question.TYPE_CHOICE
    question.save()
    res['positions'][0]['answers'][0]['options'] = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [
        {'answers': [{'non_field_errors': ['You need to specify options if the question is of a choice type.']}]}]}

    with scopes_disabled():
        question2.options.create(answer="L")
    with scopes_disabled():
        res['positions'][0]['answers'][0]['options'] = [
            question2.options.first().pk,
        ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [{'answers': [{'non_field_errors': ['The specified option does not belong to this question.']}]}]}

    with scopes_disabled():
        question.options.create(answer="L")
    with scopes_disabled():
        res['positions'][0]['answers'][0]['options'] = [
            question.options.first().pk,
            question.options.last().pk,
        ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [{'answers': [{'non_field_errors': ['You can specify at most one option for this question.']}]}]}

    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'image/png',
            'file': ContentFile(SAMPLE_PNG)
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.png"',
    )
    assert r.status_code == 201
    file_id_png = r.data['id']
    res['positions'][0]['answers'][0]['options'] = []
    res['positions'][0]['answers'][0]['answer'] = file_id_png
    question.type = Question.TYPE_FILE
    question.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        pos = o.positions.first()
        answ = pos.answers.first()
    assert answ.file
    assert answ.answer.startswith("file://")

    question.type = Question.TYPE_CHOICE_MULTIPLE
    question.save()
    with scopes_disabled():
        res['positions'][0]['answers'][0]['options'] = [
            question.options.first().pk,
            question.options.last().pk,
        ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        pos = o.positions.first()
        answ = pos.answers.first()
    assert answ.question == question
    assert answ.answer == "XL, L"

    question.type = Question.TYPE_NUMBER
    question.save()
    res['positions'][0]['answers'][0]['options'] = []
    res['positions'][0]['answers'][0]['answer'] = '3.45'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        pos = o.positions.first()
        answ = pos.answers.first()
    assert answ.answer == "3.45"

    question.type = Question.TYPE_NUMBER
    question.save()
    res['positions'][0]['answers'][0]['options'] = []
    res['positions'][0]['answers'][0]['answer'] = 'foo'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'answers': [{'non_field_errors': ['A valid number is required.']}]}]}

    question.type = Question.TYPE_BOOLEAN
    question.save()
    res['positions'][0]['answers'][0]['options'] = []
    res['positions'][0]['answers'][0]['answer'] = 'True'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        pos = o.positions.first()
        answ = pos.answers.first()
    assert answ.answer == "True"

    question.type = Question.TYPE_BOOLEAN
    question.save()
    res['positions'][0]['answers'][0]['answer'] = '0'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        pos = o.positions.first()
        answ = pos.answers.first()
    assert answ.answer == "False"

    question.type = Question.TYPE_BOOLEAN
    question.save()
    res['positions'][0]['answers'][0]['answer'] = 'bla'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [{'answers': [{'non_field_errors': ['Please specify "true" or "false" for boolean questions.']}]}]}

    question.type = Question.TYPE_DATE
    question.save()
    res['positions'][0]['answers'][0]['answer'] = '2018-05-14'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        pos = o.positions.first()
        answ = pos.answers.first()
    assert answ.answer == "2018-05-14"

    question.type = Question.TYPE_DATE
    question.save()
    res['positions'][0]['answers'][0]['answer'] = 'bla'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'answers': [
        {'non_field_errors': ['Date has wrong format. Use one of these formats instead: YYYY-MM-DD.']}]}]}

    question.type = Question.TYPE_DATETIME
    question.save()
    res['positions'][0]['answers'][0]['answer'] = '2018-05-14T13:00:00Z'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        pos = o.positions.first()
        answ = pos.answers.first()
    assert answ.answer == "2018-05-14 13:00:00+00:00"

    question.type = Question.TYPE_DATETIME
    question.save()
    res['positions'][0]['answers'][0]['answer'] = 'bla'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'answers': [{'non_field_errors': [
        'Datetime has wrong format. Use one of these formats instead: '
        'YYYY-MM-DDThh:mm[:ss[.uuuuuu]][+HH:MM|-HH:MM|Z].']}]}]}

    question.type = Question.TYPE_TIME
    question.save()
    res['positions'][0]['answers'][0]['answer'] = '13:00:00'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        pos = o.positions.first()
        answ = pos.answers.first()
    assert answ.answer == "13:00:00"

    question.type = Question.TYPE_TIME
    question.save()
    res['positions'][0]['answers'][0]['answer'] = 'bla'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'answers': [
        {'non_field_errors': ['Time has wrong format. Use one of these formats instead: hh:mm[:ss[.uuuuuu]].']}]}]}


@pytest.mark.django_db
def test_order_create_quota_validation(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None
        },
        {
            "positionid": 2,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": 1,
            "answers": [],
            "subevent": None
        }
    ]

    quota.size = 0
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'item': ['There is not enough quota available on quota "Budget Quota" to perform the operation.']},
            {'item': ['There is not enough quota available on quota "Budget Quota" to perform the operation.']},
        ]
    }

    quota.size = 1
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {},
            {'item': ['There is not enough quota available on quota "Budget Quota" to perform the operation.']},
        ]
    }

    res['force'] = True
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_order_create_quota_consume_cart(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk

    with scopes_disabled():
        cr = CartPosition.objects.create(
            event=event, cart_id="uxLJBUMEcnxOLI2EuxLYN1hWJq9GKu4yWL9FEgs2m7M0vdFi@api", item=item,
            price=23,
            expires=now() + datetime.timedelta(hours=3)
        )

    quota.size = 1
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'item': ['There is not enough quota available on quota "Budget Quota" to perform the operation.']},
        ]
    }

    res['consume_carts'] = [cr.cart_id]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        assert not CartPosition.objects.filter(pk=cr.pk).exists()


@pytest.mark.django_db
def test_order_create_quota_consume_cart_expired(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk

    with scopes_disabled():
        cr = CartPosition.objects.create(
            event=event, cart_id="uxLJBUMEcnxOLI2EuxLYN1hWJq9GKu4yWL9FEgs2m7M0vdFi@api", item=item,
            price=23,
            expires=now() - datetime.timedelta(hours=3)
        )

    quota.size = 0
    quota.save()
    res['consume_carts'] = [cr.cart_id]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'item': ['There is not enough quota available on quota "Budget Quota" to perform the operation.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_free(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'] = []
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['price'] = '0.00'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
    assert o.total == Decimal('0.00')
    assert o.status == Order.STATUS_PAID

    with scopes_disabled():
        p = o.payments.first()
    assert p.provider == "free"
    assert p.amount == o.total
    assert p.state == "confirmed"
    assert o.all_logentries().count() == 3


@pytest.mark.django_db
def test_order_create_invalid_payment_provider(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['payment_provider'] = 'foo'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'payment_provider': ['The given payment provider is not known.']}


@pytest.mark.django_db
def test_order_create_invalid_free_order(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['payment_provider'] = 'free'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == ['You cannot use the "free" payment provider for non-free orders.']


@pytest.mark.django_db
def test_order_create_invalid_status(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['status'] = 'e'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'status': ['"e" is not a valid choice.']}


@pytest.mark.django_db
def test_order_create_paid_generate_invoice(token_client, organizer, event, item, quota, question):
    event.settings.invoice_generate = 'paid'
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['status'] = 'p'
    res['payment_date'] = '2019-04-01 08:20:00Z'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.invoices.count() == 1

        p = o.payments.first()
    assert p.provider == "banktransfer"
    assert p.amount == o.total
    assert p.state == "confirmed"
    assert p.payment_date.year == 2019
    assert p.payment_date.month == 4
    assert p.payment_date.day == 1
    assert p.payment_date.hour == 8
    assert p.payment_date.minute == 20


@pytest.fixture
def seat(event, organizer, item):
    SeatingPlan.objects.create(
        name="Plan", organizer=organizer, layout="{}"
    )
    event.seat_category_mappings.create(
        layout_category='Stalls', product=item
    )
    return event.seats.create(seat_number="A1", product=item, seat_guid="A1")


@pytest.mark.django_db
def test_order_create_with_seat(token_client, organizer, event, item, quota, seat, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['seat'] = seat.seat_guid
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.seat == seat


@pytest.mark.django_db
def test_order_create_with_blocked_seat_allowed(token_client, organizer, event, item, quota, seat, question):
    seat.blocked = True
    seat.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['seat'] = seat.seat_guid
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['sales_channel'] = 'bar'
    event.settings.seating_allow_blocked_seats_for_channel = ['bar']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_order_create_with_blocked_seat(token_client, organizer, event, item, quota, seat, question):
    seat.blocked = True
    seat.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['seat'] = seat.seat_guid
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'seat': ['The selected seat "Seat A1" is not available.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_with_used_seat(token_client, organizer, event, item, quota, seat, question):
    CartPosition.objects.create(
        event=event, cart_id='aaa', item=item,
        price=21.5, expires=now() + datetime.timedelta(minutes=10), seat=seat
    )
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['seat'] = seat.seat_guid
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'seat': ['The selected seat "Seat A1" is not available.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_with_unknown_seat(token_client, organizer, event, item, quota, seat, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['seat'] = seat.seat_guid + '_'
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'seat': ['The specified seat does not exist.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_require_seat(token_client, organizer, event, item, quota, seat, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'seat': ['The specified product requires to choose a seat.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_unseated(token_client, organizer, event, item, quota, seat, question):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        quota.items.add(item2)
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item2.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['seat'] = seat.seat_guid
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'seat': ['The specified product does not allow to choose a seat.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_with_duplicate_seat(token_client, organizer, event, item, quota, seat, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None,
            "seat": seat.seat_guid
        },
        {
            "positionid": 2,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None,
            "seat": seat.seat_guid
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {},
            {'seat': ['The selected seat "Seat A1" is not available.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_with_seat_consumed_from_cart(token_client, organizer, event, item, quota, seat, question):
    CartPosition.objects.create(
        event=event, cart_id='aaa', item=item,
        price=21.5, expires=now() + datetime.timedelta(minutes=10), seat=seat
    )
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['seat'] = seat.seat_guid
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['consume_carts'] = ['aaa']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.seat == seat


@pytest.mark.django_db
def test_order_create_with_voucher_consumed_from_cart(token_client, organizer, event, item, quota, question):
    with scopes_disabled():
        voucher = event.vouchers.create(code="FOOBAR", item=item, max_usages=3, redeemed=2)
    CartPosition.objects.create(
        event=event, cart_id='aaa', item=item, voucher=voucher,
        price=21.5, expires=now() + datetime.timedelta(minutes=10),
    )
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['voucher'] = voucher.code
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['consume_carts'] = ['aaa']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.voucher == voucher


@pytest.mark.django_db
def test_order_create_send_no_emails(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_order_create_send_emails(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['send_email'] = True
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Your order: {}".format(resp.data['code'])


@pytest.mark.django_db
def test_order_create_send_emails_free(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['price'] = '0.00'
    res['payment_provider'] = 'free'
    del res['fees']
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['send_email'] = True
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Your order: {}".format(resp.data['code'])


@pytest.mark.django_db
def test_order_create_send_emails_based_on_sales_channel(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['price'] = '0.00'
    res['payment_provider'] = 'free'
    del res['fees']
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['send_email'] = None
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Your order: {}".format(resp.data['code'])

    event.settingsmail_sales_channel_placed_paid = []
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_order_create_send_emails_paid(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['send_email'] = True
    res['status'] = 'p'
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert len(djmail.outbox) == 2
    assert djmail.outbox[0].subject == "Your order: {}".format(resp.data['code'])
    assert djmail.outbox[1].subject == "Payment received for your order: {}".format(resp.data['code'])


@pytest.mark.django_db
def test_order_create_send_emails_legacy(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['send_mail'] = True
    res['status'] = 'p'
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert len(djmail.outbox) == 2
    assert djmail.outbox[0].subject == "Your order: {}".format(resp.data['code'])
    assert djmail.outbox[1].subject == "Payment received for your order: {}".format(resp.data['code'])


@pytest.mark.django_db
def test_order_paid_require_payment_method(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['payment_provider']
    res['status'] = 'p'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == [
        'You cannot create a paid order without a payment provider.'
    ]

    res['status'] = "n"
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert not o.payments.exists()


@pytest.mark.django_db
def test_order_create_auto_validity(token_client, organizer, event, item, quota, question):
    item.validity_mode = 'dynamic'
    item.validity_dynamic_duration_minutes = 30
    item.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert now() - datetime.timedelta(seconds=30) < p.valid_from <= now()
    assert now() + datetime.timedelta(minutes=29) < p.valid_until < now() + datetime.timedelta(minutes=31)


@pytest.mark.django_db
def test_order_create_manual_validity_precedence(token_client, organizer, event, item, quota, question):
    item.validity_mode = 'dynamic'
    item.validity_dynamic_duration_minutes = 30
    item.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['valid_from'] = '2022-01-01T09:00:00.000Z'
    res['positions'][0]['valid_until'] = '2022-01-03T09:00:00.000Z'
    del res['positions'][0]['price']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.valid_from.isoformat() == '2022-01-01T09:00:00+00:00'
    assert p.valid_until.isoformat() == '2022-01-03T09:00:00+00:00'


@pytest.mark.django_db
def test_order_create_auto_validity_with_requested_start(token_client, organizer, event, item, quota, question):
    item.validity_mode = 'dynamic'
    item.validity_dynamic_duration_minutes = 30
    item.validity_dynamic_start_choice = True
    item.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['requested_valid_from'] = '2039-01-01T09:00:00.000Z'
    del res['positions'][0]['price']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.valid_from.isoformat() == '2039-01-01T09:00:00+00:00'
    assert p.valid_until.isoformat() == '2039-01-01T09:30:00+00:00'


@pytest.mark.django_db
def test_order_create_auto_validity_with_requested_start_limitation(token_client, organizer, event, item, quota, question):
    item.validity_mode = 'dynamic'
    item.validity_dynamic_duration_minutes = 30
    item.validity_dynamic_start_choice = True
    item.validity_dynamic_start_choice_day_limit = 24
    item.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['requested_valid_from'] = (now() + datetime.timedelta(days=30)).isoformat()
    del res['positions'][0]['price']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert now() + datetime.timedelta(days=23) < p.valid_from <= now() + datetime.timedelta(days=26)
    assert p.valid_until == p.valid_from + datetime.timedelta(minutes=30)


@pytest.mark.django_db
def test_order_create_auto_pricing(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.price == item.default_price
    assert o.total == item.default_price + Decimal('0.25')


@pytest.mark.django_db
def test_order_create_auto_pricing_reverse_charge(token_client, organizer, event, item, quota, question, taxrule):
    taxrule.eu_reverse_charge = True
    taxrule.home_country = Country('DE')
    taxrule.save()
    item.tax_rule = taxrule
    item.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['invoice_address']['country'] = 'FR'
    res['invoice_address']['is_business'] = True
    res['invoice_address']['vat_id'] = 'FR12345'
    res['invoice_address']['vat_id_validated'] = True
    del res['positions'][0]['price']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.price == Decimal('19.33')
    assert p.tax_rate == Decimal('0.00')
    assert p.tax_value == Decimal('0.00')
    assert o.total == Decimal('19.58')


@pytest.mark.django_db
def test_order_create_auto_pricing_country_rate(token_client, organizer, event, item, quota, question, taxrule):
    taxrule.eu_reverse_charge = True
    taxrule.custom_rules = json.dumps([
        {'country': 'FR', 'address_type': '', 'action': 'vat', 'rate': '100.00'}
    ])
    taxrule.save()
    item.tax_rule = taxrule
    item.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['invoice_address']['country'] = 'FR'
    res['invoice_address']['is_business'] = True
    res['invoice_address']['vat_id'] = 'FR12345'
    res['invoice_address']['vat_id_validated'] = True
    del res['positions'][0]['price']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.price == Decimal('38.66')
    assert p.tax_rate == Decimal('100.00')
    assert p.tax_value == Decimal('19.33')
    assert o.total == Decimal('38.91')


@pytest.mark.django_db
def test_order_create_auto_pricing_reverse_charge_require_valid_vatid(token_client, organizer, event, item, quota,
                                                                      question, taxrule):
    taxrule.eu_reverse_charge = True
    taxrule.home_country = Country('DE')
    taxrule.save()
    item.tax_rule = taxrule
    item.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['invoice_address']['country'] = 'FR'
    res['invoice_address']['is_business'] = True
    res['invoice_address']['vat_id'] = 'FR12345'
    del res['positions'][0]['price']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.price == Decimal('23.00')
    assert p.tax_rate == Decimal('19.00')


@pytest.mark.django_db
def test_order_create_autopricing_voucher_budget_partially(token_client, organizer, event, item, quota, question,
                                                           taxrule):
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=21.50, item=item, budget=Decimal('2.50'),
                                        max_usages=999)
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['voucher'] = voucher.code
    del res['positions'][0]['price']
    del res['positions'][0]['positionid']
    res['positions'].append(res['positions'][0])

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
        p2 = o.positions.last()
    assert p.price == Decimal('21.50')
    assert p2.price == Decimal('22.00')


@pytest.mark.django_db
def test_order_create_autopricing_voucher_budget_full(token_client, organizer, event, item, quota, question, taxrule):
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=21.50, item=item, budget=Decimal('0.50'),
                                        max_usages=999)
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['voucher'] = voucher.code
    del res['positions'][0]['price']
    del res['positions'][0]['positionid']
    res['positions'].append(res['positions'][0])

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{}, {'voucher': ['The voucher has a remaining budget of 0.00, therefore a '
                                                        'discount of 1.50 can not be given.']}]}


@pytest.mark.django_db
def test_order_create_voucher_budget_exceeded(token_client, organizer, event, item, quota, question, taxrule):
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=21.50, item=item, budget=Decimal('3.00'),
                                        max_usages=999)
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['voucher'] = voucher.code
    res['positions'][0]['price'] = '19.00'
    del res['positions'][0]['positionid']

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'voucher': ['The voucher has a remaining budget of 3.00, therefore a '
                                                    'discount of 4.00 can not be given.']}]}


@pytest.mark.django_db
def test_order_create_voucher_price(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=15, item=item)
    res['positions'][0]['voucher'] = voucher.code
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.voucher == voucher
    voucher.refresh_from_db()
    assert voucher.redeemed == 1
    assert p.price == Decimal('15.00')
    assert o.total == Decimal('15.25')


@pytest.mark.django_db
def test_order_create_voucher_unknown_code(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    with scopes_disabled():
        event.vouchers.create(price_mode="set", value=15, item=item)
    res['positions'][0]['voucher'] = "FOOBAR"
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'voucher': ['Object with code=FOOBAR does not exist.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_voucher_redeemed(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    del res['positions'][0]['price']
    res['positions'][0]['answers'][0]['question'] = question.pk
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=15, item=item, redeemed=1)
    res['positions'][0]['voucher'] = voucher.code
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'voucher': ['The voucher has already been used the maximum number of times.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_voucher_redeemed_partially(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['item'] = item.pk
    del res['positions'][0]['price']
    del res['positions'][0]['positionid']
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=15, item=item, redeemed=1, max_usages=2)
    res['positions'][0]['voucher'] = voucher.code
    res['positions'].append(copy.deepcopy(res['positions'][0]))
    res['positions'].append(copy.deepcopy(res['positions'][0]))
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {},
            {'voucher': ['The voucher has already been used the maximum number of times.']},
            {'voucher': ['The voucher has already been used the maximum number of times.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_voucher_item_mismatch(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        voucher = event.vouchers.create(price_mode="set", value=15, item=item2, redeemed=0)
    res['positions'][0]['voucher'] = voucher.code
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'voucher': ['This voucher is not valid for this product.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_voucher_expired(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=15, item=item, redeemed=0,
                                        valid_until=now() - datetime.timedelta(days=1))
    res['positions'][0]['voucher'] = voucher.code
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'voucher': ['This voucher is expired.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_voucher_block_quota(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    quota.size = 0
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400

    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=15, item=item, redeemed=0,
                                        block_quota=True)
    res['positions'][0]['voucher'] = voucher.code
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_order_create_pdf_data(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    with scopes_disabled():
        customer = organizer.customers.create()
    res['customer'] = customer.identifier
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/?pdf_data=true'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert 'secret' in resp.data['positions'][0]['pdf_data']


@pytest.mark.django_db
def test_create_cart_and_consume_cart_with_addons(token_client, organizer, event, item, quota, question):
    # End to end test for the combination of cart creation and order creation, as used eg in POS
    with scopes_disabled():
        addon_cat = event.categories.create(name='Addons')
        addon_item = event.items.create(name='Workshop', default_price=2, category=addon_cat)
        item.addons.create(addon_category=addon_cat)
        q = event.quotas.create(name="Addon Quota", size=1)
        q.items.add(addon_item)

    res = {
        'cart_id': 'aaa@api',
        'item': item.pk,
        'variation': None,
        'price': '23.00',
        'attendee_name_parts': {'full_name': 'Peter'},
        'attendee_email': None,
        'addon_to': None,
        'subevent': None,
        'expires': (now() + datetime.timedelta(days=1)).isoformat(),
        'includes_tax': True,
        'sales_channel': 'web',
        'answers': [],
        'addons': [
            {
                'item': addon_item.pk,
                'variation': None,
                'price': '1.00',
                'attendee_name_parts': {'full_name': 'Peter\'s friend'},
                'attendee_email': None,
                'subevent': None,
                'includes_tax': True,
                'answers': []
            }
        ],
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/bulk_create/'.format(
            organizer.slug, event.slug
        ), format='json', data=[
            res
        ]
    )
    assert resp.status_code == 200
    assert len(resp.data['results']) == 1
    assert resp.data['results'][0]['success']
    assert resp.data['results'][0]['data']['addons']

    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None
        },
        {
            "positionid": 2,
            "item": addon_item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": 1,
            "answers": [],
            "subevent": None
        }
    ]

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {},
            {'item': ['There is not enough quota available on quota "Addon Quota" to perform the operation.']},
        ]
    }

    res['consume_carts'] = ['aaa@api']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_order_create_use_medium(token_client, organizer, event, item, quota, question, medium):
    item.media_type = medium.type
    item.media_policy = Item.MEDIA_POLICY_REUSE_OR_NEW
    item.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['use_reusable_medium'] = medium.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/?pdf_data=true'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        medium.refresh_from_db()
        assert o.positions.first() == medium.linked_orderposition
        assert resp.data['positions'][0]['pdf_data']['medium_identifier'] == medium.identifier


@pytest.mark.django_db
def test_order_create_use_medium_other_organizer(token_client, organizer, event, item, quota, question, medium2):
    item.media_type = medium2.type
    item.media_policy = Item.MEDIA_POLICY_REUSE_OR_NEW
    item.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['use_reusable_medium'] = medium2.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/?pdf_data=true'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.data == {
        "positions": [
            {
                "use_reusable_medium": ["The specified medium does not belong to this organizer."]
            }
        ]
    }
    assert resp.status_code == 400


@pytest.mark.django_db
def test_order_create_create_medium(token_client, organizer, event, item, quota, question):
    item.media_type = 'barcode'
    item.media_policy = Item.MEDIA_POLICY_REUSE_OR_NEW
    item.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/?pdf_data=true'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        i = resp.data['positions'][0]['pdf_data']['medium_identifier']
        assert i
        m = organizer.reusable_media.get(identifier=i)
        assert m.linked_orderposition == o.positions.first()
        assert m.type == "barcode"
