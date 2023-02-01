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
import datetime
from decimal import Decimal
from unittest import mock

import freezegun
import pytest
from django_countries.fields import Country
from django_scopes import scopes_disabled

from pretix.base.models import InvoiceAddress, Order, OrderPosition
from pretix.base.models.orders import OrderFee
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice,
)


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
def invoice(order):
    testtime = datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=datetime.timezone.utc)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        return generate_invoice(order)


TEST_INVOICE_RES = {
    "order": "FOO",
    "number": "DUMMY-00001",
    "is_cancellation": False,
    "invoice_from_name": "",
    "invoice_from": "",
    "invoice_from_zipcode": "",
    "invoice_from_city": "",
    "invoice_from_country": None,
    "invoice_from_tax_id": "",
    "invoice_from_vat_id": "",
    "invoice_to": "Sample company\nNew Zealand\nVAT-ID: DE123",
    "invoice_to_company": "Sample company",
    "invoice_to_name": "",
    "invoice_to_street": "",
    "invoice_to_zipcode": "",
    "invoice_to_city": "",
    "invoice_to_state": "",
    "invoice_to_country": "NZ",
    "invoice_to_vat_id": "DE123",
    "invoice_to_beneficiary": "",
    "custom_field": None,
    "date": "2017-12-10",
    "refers": None,
    "locale": "en",
    "introductory_text": "",
    "internal_reference": "",
    "additional_text": "",
    "payment_provider_text": "",
    "payment_provider_stamp": None,
    "footer_text": "",
    "foreign_currency_display": None,
    "foreign_currency_rate": None,
    "foreign_currency_rate_date": None,
    "lines": [
        {
            "position": 1,
            "description": "Budget Ticket<br />Attendee: Peter",
            'subevent': None,
            'event_date_from': '2017-12-27T10:00:00Z',
            'event_date_to': None,
            'event_location': None,
            'attendee_name': 'Peter',
            'item': None,
            'variation': None,
            'fee_type': None,
            'fee_internal_type': None,
            "gross_value": "23.00",
            "tax_value": "0.00",
            "tax_name": "",
            "tax_rate": "0.00"
        },
        {
            "position": 2,
            "description": "Payment fee",
            'subevent': None,
            'event_date_from': '2017-12-27T10:00:00Z',
            'event_date_to': None,
            'event_location': None,
            'attendee_name': None,
            'fee_type': "payment",
            'fee_internal_type': None,
            'item': None,
            'variation': None,
            "gross_value": "0.25",
            "tax_value": "0.05",
            "tax_name": "",
            "tax_rate": "19.00"
        }
    ]
}


@pytest.mark.django_db
def test_invoice_list(token_client, organizer, event, order, item, invoice):
    res = dict(TEST_INVOICE_RES)
    res['lines'][0]['item'] = item.pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?order=FOO'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?order=BAR'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?number={}'.format(
        organizer.slug, event.slug, invoice.number))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?number=XXX'.format(
        organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?locale=en'.format(
        organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?locale=de'.format(
        organizer.slug, event.slug))
    assert [] == resp.data['results']

    with scopes_disabled():
        ic = generate_cancellation(invoice)

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?is_cancellation=false'.format(
        organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?is_cancellation=true'.format(
        organizer.slug, event.slug))
    assert len(resp.data['results']) == 1
    assert resp.data['results'][0]['number'] == ic.number

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?refers={}'.format(
        organizer.slug, event.slug, invoice.number))
    assert len(resp.data['results']) == 1
    assert resp.data['results'][0]['number'] == ic.number

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?refers={}'.format(
        organizer.slug, event.slug, ic.number))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_invoice_detail(token_client, organizer, event, item, invoice):
    res = dict(TEST_INVOICE_RES)
    res['lines'][0]['item'] = item.pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/{}/'.format(organizer.slug, event.slug,
                                                                                  invoice.number))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_invoice_regenerate(token_client, organizer, event, invoice):
    organizer.settings.invoice_regenerate_allowed = True
    with scopes_disabled():
        InvoiceAddress.objects.filter(order=invoice.order).update(company="ACME Ltd")

    with freezegun.freeze_time("2017-12-10"):
        resp = token_client.post('/api/v1/organizers/{}/events/{}/invoices/{}/regenerate/'.format(
            organizer.slug, event.slug, invoice.number
        ))
        assert resp.status_code == 204
        invoice.refresh_from_db()
        assert "ACME Ltd" in invoice.invoice_to


@pytest.mark.django_db
def test_invoice_reissue(token_client, organizer, event, invoice):
    with scopes_disabled():
        InvoiceAddress.objects.filter(order=invoice.order).update(company="ACME Ltd")

    resp = token_client.post('/api/v1/organizers/{}/events/{}/invoices/{}/reissue/'.format(
        organizer.slug, event.slug, invoice.number
    ))
    assert resp.status_code == 204
    invoice.refresh_from_db()
    assert "ACME Ltd" not in invoice.invoice_to
    with scopes_disabled():
        assert invoice.order.invoices.count() == 3
        invoice = invoice.order.invoices.last()
    assert "ACME Ltd" in invoice.invoice_to
