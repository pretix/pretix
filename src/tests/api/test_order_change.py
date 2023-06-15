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
    InvoiceAddress, Order, OrderPosition, Question, SeatingPlan,
)
from pretix.base.models.orders import OrderFee
from pretix.base.services.invoices import generate_invoice


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
def seat(event, organizer, item):
    SeatingPlan.objects.create(
        name="Plan", organizer=organizer, layout="{}"
    )
    event.seat_category_mappings.create(
        layout_category='Stalls', product=item
    )
    return event.seats.create(seat_number="A1", product=item, seat_guid="A1")


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


@pytest.mark.django_db
def test_order_update_ignore_fields(token_client, organizer, event, order):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'status': 'c'
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == 'n'


@pytest.mark.django_db
def test_order_update_only_partial(token_client, organizer, event, order):
    resp = token_client.put(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'status': 'c'
        }
    )
    assert resp.status_code == 405


@pytest.mark.django_db
def test_order_update_state_validation(token_client, organizer, event, order):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'invoice_address': {
                "is_business": False,
                "company": "This is my company name",
                "name": "John Doe",
                "name_parts": {},
                "street": "",
                "state": "",
                "zipcode": "",
                "city": "Paris",
                "country": "NONEXISTANT",
                "internal_reference": "",
                "vat_id": "",
            }
        }
    )
    assert resp.status_code == 400
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'invoice_address': {
                "is_business": False,
                "company": "This is my company name",
                "name": "John Doe",
                "name_parts": {},
                "street": "",
                "state": "NONEXISTANT",
                "zipcode": "",
                "city": "Test",
                "country": "AU",
                "internal_reference": "",
                "vat_id": "",
            }
        }
    )
    assert resp.status_code == 400

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'invoice_address': {
                "is_business": False,
                "company": "This is my company name",
                "name": "John Doe",
                "name_parts": {},
                "street": "",
                "state": "QLD",
                "zipcode": "",
                "city": "Test",
                "country": "AU",
                "internal_reference": "",
                "vat_id": "",
            }
        }
    )
    assert resp.status_code == 200
    order.invoice_address.refresh_from_db()
    assert order.invoice_address.state == "QLD"
    assert order.invoice_address.country == "AU"


@pytest.mark.django_db
def test_order_update_allowed_fields(token_client, organizer, event, order):
    event.settings.locales = ['de', 'en']
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'comment': 'Here is a comment',
            'valid_if_pending': True,
            'custom_followup_at': '2021-06-12',
            'checkin_attention': True,
            'email': 'foo@bar.com',
            'phone': '+4962219999',
            'locale': 'de',
            'invoice_address': {
                "is_business": False,
                "company": "This is my company name",
                "name": "John Doe",
                "name_parts": {},
                "street": "",
                "state": "",
                "zipcode": "",
                "city": "Paris",
                "country": "FR",
                "internal_reference": "",
                "vat_id": "",
            }
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.comment == 'Here is a comment'
    assert order.custom_followup_at.isoformat() == '2021-06-12'
    assert order.checkin_attention
    assert order.email == 'foo@bar.com'
    assert order.phone == '+4962219999'
    assert order.locale == 'de'
    assert order.valid_if_pending
    assert order.invoice_address.company == "This is my company name"
    assert order.invoice_address.name_cached == "John Doe"
    assert order.invoice_address.name_parts == {'_legacy': 'John Doe'}
    assert str(order.invoice_address.country) == "FR"
    assert not order.invoice_address.vat_id_validated
    assert order.invoice_address.city == "Paris"
    with scopes_disabled():
        assert order.all_logentries().get(action_type='pretix.event.order.comment')
        assert order.all_logentries().get(action_type='pretix.event.order.custom_followup_at')
        assert order.all_logentries().get(action_type='pretix.event.order.checkin_attention')
        assert order.all_logentries().get(action_type='pretix.event.order.contact.changed')
        assert order.all_logentries().get(action_type='pretix.event.order.phone.changed')
        assert order.all_logentries().get(action_type='pretix.event.order.locale.changed')
        assert order.all_logentries().get(action_type='pretix.event.order.modified')


@pytest.mark.django_db
def test_order_update_validated_vat_id(token_client, organizer, event, order):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'invoice_address': {
                "is_business": False,
                "company": "This is my company name",
                "name": "John Doe",
                "name_parts": {},
                "street": "",
                "state": "",
                "zipcode": "",
                "city": "Paris",
                "country": "FR",
                "internal_reference": "",
                "vat_id": "FR123",
                "vat_id_validated": True
            }
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.invoice_address.vat_id == "FR123"
    assert order.invoice_address.vat_id_validated


@pytest.mark.django_db
def test_order_update_invoiceaddress_delete_create(token_client, organizer, event, order):
    event.settings.locales = ['de', 'en']
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'invoice_address': None,
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    with pytest.raises(InvoiceAddress.DoesNotExist):
        order.invoice_address

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'invoice_address': {
                "is_business": False,
                "company": "This is my company name",
                "name": "",
                "name_parts": {},
                "street": "",
                "state": "",
                "zipcode": "",
                "city": "Paris",
                "country": "Fr",
                "internal_reference": "",
                "vat_id": "",
            }
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.invoice_address.company == "This is my company name"
    assert str(order.invoice_address.country) == "FR"
    assert order.invoice_address.city == "Paris"


@pytest.mark.django_db
def test_order_update_email_to_none(token_client, organizer, event, order):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'email': None,
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.email is None


@pytest.mark.django_db
def test_order_update_locale_to_invalid(token_client, organizer, event, order):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'locale': 'de',
        }
    )
    assert resp.status_code == 400
    assert resp.data == {'locale': ['"de" is not a supported locale for this event.']}


@pytest.mark.django_db
def test_order_create_invoice(token_client, organizer, event, order):
    event.settings.invoice_generate = 'True'

    event.settings.invoice_generate_sales_channels = []

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/create_invoice/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.status_code == 400

    event.settings.invoice_generate_sales_channels = ['web']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/create_invoice/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.status_code == 201
    with scopes_disabled():
        pos = order.positions.first()
    assert json.loads(json.dumps(resp.data)) == {
        'order': 'FOO',
        'number': 'DUMMY-00001',
        'is_cancellation': False,
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
        'date': now().date().isoformat(),
        'refers': None,
        'locale': 'en',
        'introductory_text': '',
        'additional_text': '',
        'payment_provider_text': '',
        'payment_provider_stamp': None,
        'footer_text': '',
        'lines': [
            {
                'position': 1,
                'description': 'Budget Ticket<br />Attendee: Peter',
                'subevent': None,
                'event_date_from': '2017-12-27T10:00:00Z',
                'event_date_to': None,
                'event_location': None,
                'fee_type': None,
                'fee_internal_type': None,
                'attendee_name': 'Peter',
                'item': pos.item_id,
                'variation': None,
                'gross_value': '23.00',
                'tax_value': '0.00',
                'tax_rate': '0.00',
                'tax_name': ''
            },
            {
                'position': 2,
                'description': 'Payment fee',
                'subevent': None,
                'event_date_from': '2017-12-27T10:00:00Z',
                'event_date_to': None,
                'event_location': None,
                'fee_type': "payment",
                'fee_internal_type': None,
                'attendee_name': None,
                'item': None,
                'variation': None,
                'gross_value': '0.25',
                'tax_value': '0.05',
                'tax_rate': '19.00',
                'tax_name': ''
            }
        ],
        'foreign_currency_display': None,
        'foreign_currency_rate': None,
        'foreign_currency_rate_date': None,
        'internal_reference': ''
    }

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/create_invoice/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.data == {'detail': 'An invoice for this order already exists.'}
    assert resp.status_code == 400

    event.settings.invoice_generate = 'False'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/create_invoice/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.status_code == 400
    assert resp.data == {'detail': 'You cannot generate an invoice for this order.'}


@pytest.mark.django_db
def test_order_regenerate_secrets(token_client, organizer, event, order):
    s = order.secret
    with scopes_disabled():
        ps = order.positions.first().secret
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/regenerate_secrets/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert s != order.secret
    with scopes_disabled():
        assert ps != order.positions.first().secret


@pytest.mark.django_db
def test_position_regenerate_secrets(token_client, organizer, event, order):
    with scopes_disabled():
        p = order.positions.first()
        ps = p.secret
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/regenerate_secrets/'.format(
            organizer.slug, event.slug, p.pk,
        ), format='json', data={}
    )
    assert resp.status_code == 200
    p.refresh_from_db()
    with scopes_disabled():
        assert ps != p.secret


@pytest.mark.django_db
def test_position_manage_blocks(token_client, organizer, event, order):
    with scopes_disabled():
        p = order.positions.first()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/add_block/'.format(
            organizer.slug, event.slug, p.pk,
        ), format='json', data={
            'name': 'invalid'
        }
    )
    assert resp.status_code == 400

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/add_block/'.format(
            organizer.slug, event.slug, p.pk,
        ), format='json', data={
            'name': 'admin'
        }
    )
    assert resp.status_code == 200
    p.refresh_from_db()
    assert p.blocked == ['admin']

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/add_block/'.format(
            organizer.slug, event.slug, p.pk,
        ), format='json', data={
            'name': 'api:custom'
        }
    )
    assert resp.status_code == 200
    p.refresh_from_db()
    assert p.blocked == ['admin', 'api:custom']

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/remove_block/'.format(
            organizer.slug, event.slug, p.pk,
        ), format='json', data={
            'name': 'api:custom'
        }
    )
    assert resp.status_code == 200
    p.refresh_from_db()
    assert p.blocked == ['admin']

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/remove_block/'.format(
            organizer.slug, event.slug, p.pk,
        ), format='json', data={
            'name': 'admin'
        }
    )
    assert resp.status_code == 200
    p.refresh_from_db()
    assert p.blocked is None


@pytest.mark.django_db
def test_order_resend_link(token_client, organizer, event, order):
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/resend_link/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.status_code == 204
    assert len(djmail.outbox) == 1

    order.email = None
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/resend_link/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_orderposition_price_calculation(token_client, organizer, event, order, item):
    with scopes_disabled():
        op = order.positions.first()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('23.00'),
        'gross_formatted': '23.00',
        'name': '',
        'net': Decimal('23.00'),
        'rate': Decimal('0.00'),
        'tax_rule': None,
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_item_with_tax(token_client, organizer, event, order, item, taxrule):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23, tax_rule=taxrule)
        op = order.positions.first()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('23.00'),
        'gross_formatted': '23.00',
        'name': '',
        'net': Decimal('19.33'),
        'rate': Decimal('19.00'),
        'tax_rule': taxrule.pk,
        'tax': Decimal('3.67')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_item_with_variation(token_client, organizer, event, order):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        var = item2.variations.create(default_price=12, value="XS")
        op = order.positions.first()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
            'variation': var.pk
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('12.00'),
        'gross_formatted': '12.00',
        'name': '',
        'net': Decimal('12.00'),
        'rate': Decimal('0.00'),
        'tax_rule': None,
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_subevent(token_client, organizer, event, order, subevent):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        op = order.positions.first()
    op.subevent = subevent
    op.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
            'subevent': subevent.pk
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('23.00'),
        'gross_formatted': '23.00',
        'name': '',
        'net': Decimal('23.00'),
        'rate': Decimal('0.00'),
        'tax_rule': None,
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_subevent_with_override(token_client, organizer, event, order, subevent):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        se2 = event.subevents.create(name="Foobar", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=datetime.timezone.utc))
        se2.subeventitem_set.create(item=item2, price=12)
        op = order.positions.first()
    op.subevent = subevent
    op.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
            'subevent': se2.pk
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('12.00'),
        'gross_formatted': '12.00',
        'name': '',
        'net': Decimal('12.00'),
        'rate': Decimal('0.00'),
        'tax_rule': None,
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_voucher_matching(token_client, organizer, event, order, subevent, item):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        q = event.quotas.create(name="Quota")
        q.items.add(item)
        q.items.add(item2)
        voucher = event.vouchers.create(price_mode="set", value=15, quota=q)
        op = order.positions.first()
    op.voucher = voucher
    op.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('15.00'),
        'gross_formatted': '15.00',
        'name': '',
        'net': Decimal('15.00'),
        'rate': Decimal('0.00'),
        'tax_rule': None,
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_voucher_not_matching(token_client, organizer, event, order, subevent, item):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        q = event.quotas.create(name="Quota")
        q.items.add(item)
        voucher = event.vouchers.create(price_mode="set", value=15, quota=q)
        op = order.positions.first()
    op.voucher = voucher
    op.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('23.00'),
        'gross_formatted': '23.00',
        'name': '',
        'net': Decimal('23.00'),
        'rate': Decimal('0.00'),
        'tax_rule': None,
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_net_price(token_client, organizer, event, order, subevent, item, taxrule):
    taxrule.price_includes_tax = False
    taxrule.save()
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=10, tax_rule=taxrule)
        op = order.positions.first()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('11.90'),
        'gross_formatted': '11.90',
        'name': '',
        'net': Decimal('10.00'),
        'rate': Decimal('19.00'),
        'tax_rule': taxrule.pk,
        'tax': Decimal('1.90')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_reverse_charge(token_client, organizer, event, order, subevent, item, taxrule):
    taxrule.price_includes_tax = False
    taxrule.eu_reverse_charge = True
    taxrule.home_country = Country('DE')
    taxrule.save()
    order.invoice_address.is_business = True
    order.invoice_address.vat_id = 'ATU1234567'
    order.invoice_address.vat_id_validated = True
    order.invoice_address.country = Country('AT')
    order.invoice_address.save()
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=10, tax_rule=taxrule)
        op = order.positions.first()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('10.00'),
        'gross_formatted': '10.00',
        'name': '',
        'net': Decimal('10.00'),
        'rate': Decimal('0.00'),
        'tax_rule': taxrule.pk,
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_position_update_ignore_fields(token_client, organizer, event, order):
    with scopes_disabled():
        op = order.positions.first()
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data={
            'tax_rate': '99.99'
        }
    )
    assert resp.status_code == 200
    op.refresh_from_db()
    assert op.tax_rate == Decimal('0.00')


@pytest.mark.django_db
def test_position_update_only_partial(token_client, organizer, event, order):
    with scopes_disabled():
        op = order.positions.first()
    resp = token_client.put(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data={
            'price': '99.99'
        }
    )
    assert resp.status_code == 405


@pytest.mark.django_db
def test_position_update_info(token_client, organizer, event, order, question):
    with scopes_disabled():
        op = order.positions.first()
        question.type = Question.TYPE_CHOICE_MULTIPLE
        question.save()
        opt = question.options.create(answer="L")
    payload = {
        'company': 'VILE',
        'attendee_name_parts': {
            'full_name': 'Max Mustermann'
        },
        'street': 'Sesame Street 21',
        'zipcode': '99999',
        'city': 'Springfield',
        'country': 'US',
        'state': 'CA',
        'attendee_email': 'foo@example.org',
        'answers': [
            {
                'question': question.pk,
                'answer': 'ignored',
                'options': [opt.pk]
            }
        ]
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    assert resp.data['answers'] == [
        {
            'question': question.pk,
            'question_identifier': question.identifier,
            'answer': 'L',
            'options': [opt.pk],
            'option_identifiers': [opt.identifier],
        }
    ]
    op.refresh_from_db()
    assert op.company == 'VILE'
    assert op.attendee_name_cached == 'Max Mustermann'
    assert op.attendee_name_parts == {
        '_scheme': 'full',
        'full_name': 'Max Mustermann'
    }
    with scopes_disabled():
        assert op.answers.get().answer == 'L'
        assert op.street == 'Sesame Street 21'
        assert op.zipcode == '99999'
        assert op.city == 'Springfield'
        assert str(op.country) == 'US'
        assert op.state == 'CA'
        assert op.attendee_email == 'foo@example.org'
        le = order.all_logentries().last()
    assert le.action_type == 'pretix.event.order.modified'
    assert le.parsed_data == {
        'data': [
            {
                'position': op.pk,
                'company': 'VILE',
                'attendee_name_parts': {
                    '_scheme': 'full',
                    'full_name': 'Max Mustermann'
                },
                'street': 'Sesame Street 21',
                'zipcode': '99999',
                'city': 'Springfield',
                'country': 'US',
                'state': 'CA',
                'attendee_email': 'foo@example.org',
                f'question_{question.pk}': 'L'
            }
        ]
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert order.all_logentries().last().pk == le.pk


@pytest.mark.django_db
def test_position_update_legacy_name(token_client, organizer, event, order):
    with scopes_disabled():
        op = order.positions.first()
    payload = {
        'attendee_name': 'Max Mustermann',
        'attendee_name_parts': {
            '_legacy': 'maria'
        },
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    payload = {
        'attendee_name': 'Max Mustermann',
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    op.refresh_from_db()
    assert op.attendee_name_cached == 'Max Mustermann'
    assert op.attendee_name_parts == {
        '_legacy': 'Max Mustermann'
    }
    with scopes_disabled():
        assert op.answers.count() == 1  # answer does not get deleted


@pytest.mark.django_db
def test_position_update_state_validation(token_client, organizer, event, order):
    with scopes_disabled():
        op = order.positions.first()
    payload = {
        'country': 'DE',
        'state': 'BW'
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_position_update_question_handling(token_client, organizer, event, order, question):
    with scopes_disabled():
        op = order.positions.first()
    payload = {
        'answers': [
            {
                'question': question.pk,
                'answer': 'FOOBAR',
            },
            {
                'question': question.pk,
                'answer': 'FOOBAR',
            },
        ]
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    payload = {
        'answers': [
            {
                'question': question.pk,
                'answer': 'FOOBAR',
            },
        ]
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert op.answers.count() == 1
    payload = {
        'answers': [
        ]
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert op.answers.count() == 0

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

    payload = {
        'answers': [
            {
                "question": question.id,
                "answer": file_id_png
            }
        ]
    }
    question.type = Question.TYPE_FILE
    question.save()
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    with scopes_disabled():
        answ = op.answers.get()
    assert answ.file
    assert answ.answer.startswith("file://")

    payload = {
        'answers': [
            {
                "question": question.id,
                "answer": "file:keep"
            }
        ]
    }
    question.type = Question.TYPE_FILE
    question.save()
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    with scopes_disabled():
        answ = op.answers.get()
    assert answ.file
    assert answ.answer.startswith("file://")


@pytest.mark.django_db
def test_position_update_change_item(token_client, organizer, event, order, quota):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        quota.items.add(item2)
        op = order.positions.first()
    payload = {
        'item': item2.pk,
    }
    assert op.item != item2
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    op.refresh_from_db()
    assert op.item == item2


@pytest.mark.django_db
def test_position_update_change_item_wrong_event(token_client, organizer, event, event2, order, quota):
    with scopes_disabled():
        item2 = event2.items.create(name="Budget Ticket", default_price=23)
        quota.items.add(item2)
        op = order.positions.first()
    payload = {
        'item': item2.pk,
    }
    assert op.item != item2
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    assert 'object does not exist.' in str(resp.data)


@pytest.mark.django_db
def test_position_update_change_item_no_quota(token_client, organizer, event, order):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        op = order.positions.first()
    payload = {
        'item': item2.pk,
    }
    assert op.item != item2
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    assert 'quota' in str(resp.data)


@pytest.mark.django_db
def test_position_update_change_item_variation(token_client, organizer, event, order, quota):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        v = item2.variations.create(value="foo")
        quota.items.add(item2)
        quota.variations.add(v)
        op = order.positions.first()
    payload = {
        'item': item2.pk,
        'variation': v.pk,
    }
    assert op.item != item2
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    op.refresh_from_db()
    assert op.item == item2
    assert op.variation == v


@pytest.mark.django_db
def test_position_update_change_item_variation_required(token_client, organizer, event, order, quota):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        v = item2.variations.create(value="foo")
        quota.items.add(item2)
        quota.variations.add(v)
        op = order.positions.first()
    payload = {
        'item': item2.pk,
    }
    assert op.item != item2
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    assert 'variation' in str(resp.data)


@pytest.mark.django_db
def test_position_update_change_item_variation_mismatch(token_client, organizer, event, order, quota):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        v = item2.variations.create(value="foo")
        item3 = event.items.create(name="Budget Ticket", default_price=23)
        v3 = item3.variations.create(value="foo")
        quota.items.add(item2)
        quota.items.add(item3)
        quota.variations.add(v)
        quota.variations.add(v3)
        op = order.positions.first()
    payload = {
        'item': item2.pk,
        'variation': v3.pk,
    }
    assert op.item != item2
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    assert 'variation' in str(resp.data)


@pytest.mark.django_db
def test_position_update_change_subevent(token_client, organizer, event, order, quota, item, subevent):
    with scopes_disabled():
        se2 = event.subevents.create(name="Foobar", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=datetime.timezone.utc))
        q2 = se2.quotas.create(name="foo", size=1, event=event)
        q2.items.add(item)
        op = order.positions.first()
        op.subevent = subevent
        op.save()
    payload = {
        'subevent': se2.pk,
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    op.refresh_from_db()
    assert op.subevent == se2


@pytest.mark.django_db
def test_position_update_change_subevent_quota_empty(token_client, organizer, event, order, quota, item, subevent):
    with scopes_disabled():
        se2 = event.subevents.create(name="Foobar", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=datetime.timezone.utc))
        q2 = se2.quotas.create(name="foo", size=0, event=event)
        q2.items.add(item)
        op = order.positions.first()
        op.subevent = subevent
        op.save()
    payload = {
        'subevent': se2.pk,
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    assert 'quota' in str(resp.data)


@pytest.mark.django_db
def test_position_update_change_seat(token_client, organizer, event, order, quota, item, seat):
    with scopes_disabled():
        seat2 = event.seats.create(seat_number="A2", product=item, seat_guid="A2")
        op = order.positions.first()
        op.seat = seat
        op.save()
    payload = {
        'seat': seat2.seat_guid,
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    op.refresh_from_db()
    assert op.seat == seat2


@pytest.mark.django_db
def test_position_update_unset_seat(token_client, organizer, event, order, quota, item, seat):
    with scopes_disabled():
        op = order.positions.first()
        op.seat = seat
        op.save()
    payload = {
        'seat': None,
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    op.refresh_from_db()
    assert op.seat is None


@pytest.mark.django_db
def test_position_update_change_seat_taken(token_client, organizer, event, order, quota, item, seat):
    with scopes_disabled():
        seat2 = event.seats.create(seat_number="A2", product=item, seat_guid="A2", blocked=True)
        op = order.positions.first()
        op.seat = seat
        op.save()
    payload = {
        'seat': seat2.seat_guid,
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    assert 'seat' in str(resp.data)


@pytest.mark.django_db
def test_position_update_change_subevent_keep_seat(token_client, organizer, event, order, quota, item, subevent, seat):
    with scopes_disabled():
        seat.subevent = subevent
        seat.save()
        se2 = event.subevents.create(name="Foobar", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=datetime.timezone.utc))
        seat2 = event.seats.create(seat_number="A1", product=item, seat_guid="A1", subevent=se2)
        q2 = se2.quotas.create(name="foo", size=1, event=event)
        q2.items.add(item)
        op = order.positions.first()
        op.subevent = subevent
        op.seat = seat
        op.save()
    payload = {
        'subevent': se2.pk,
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    op.refresh_from_db()
    assert op.subevent == se2
    assert op.seat == seat2


@pytest.mark.django_db
def test_position_update_change_subevent_missing_seat(token_client, organizer, event, order, quota, item, subevent, seat):
    with scopes_disabled():
        seat.subevent = subevent
        seat.save()
        se2 = event.subevents.create(name="Foobar", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=datetime.timezone.utc))
        q2 = se2.quotas.create(name="foo", size=1, event=event)
        q2.items.add(item)
        op = order.positions.first()
        op.subevent = subevent
        op.seat = seat
        op.save()
    payload = {
        'subevent': se2.pk,
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    assert 'seat' in str(resp.data)


@pytest.mark.django_db
def test_position_update_change_price(token_client, organizer, event, order, quota):
    with scopes_disabled():
        op = order.positions.first()
    payload = {
        'price': Decimal('119.00')
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    op.refresh_from_db()
    assert op.price == Decimal('119.00')
    assert op.tax_rate == Decimal('0.00')
    assert op.tax_value == Decimal('0.00')


@pytest.mark.django_db
def test_position_update_change_price_and_tax_rule(token_client, organizer, event, order, quota):
    with scopes_disabled():
        op = order.positions.first()
        tr = event.tax_rules.create(rate=19)
    payload = {
        'price': Decimal('119.00'),
        'tax_rule': tr.pk
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    op.refresh_from_db()
    assert op.price == Decimal('119.00')
    assert op.tax_rate == Decimal('19.00')
    assert op.tax_value == Decimal('19.00')
    assert op.tax_rule == tr


@pytest.mark.django_db
def test_position_add_simple(token_client, organizer, event, order, quota, item):
    with scopes_disabled():
        assert order.positions.count() == 1
    payload = {
        'order': order.code,
        'item': item.pk,
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/'.format(
            organizer.slug, event.slug,
        ), format='json', data=payload
    )
    assert resp.status_code == 201
    with scopes_disabled():
        assert order.positions.count() == 2
        op = order.positions.last()
        assert op.item == item
        assert op.price == item.default_price
        assert op.positionid == 3


@pytest.mark.django_db
def test_position_add_price(token_client, organizer, event, order, quota, item):
    with scopes_disabled():
        assert order.positions.count() == 1
    payload = {
        'order': order.code,
        'item': item.pk,
        'price': '99.99'
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/'.format(
            organizer.slug, event.slug,
        ), format='json', data=payload
    )
    assert resp.status_code == 201
    with scopes_disabled():
        assert order.positions.count() == 2
        op = order.positions.last()
        assert op.item == item
        assert op.price == Decimal('99.99')
        assert op.positionid == 3


@pytest.mark.django_db
def test_position_add_subevent(token_client, organizer, event, order, quota, item, subevent):
    with scopes_disabled():
        assert order.positions.count() == 1
        quota.subevent = subevent
        quota.save()
    payload = {
        'order': order.code,
        'item': item.pk,
        'subevent': subevent.pk,
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/'.format(
            organizer.slug, event.slug,
        ), format='json', data=payload
    )
    assert resp.status_code == 201
    with scopes_disabled():
        assert order.positions.count() == 2
        op = order.positions.last()
        assert op.item == item
        assert op.price == item.default_price
        assert op.positionid == 3
        assert op.subevent == subevent


@pytest.mark.django_db
def test_position_add_subevent_required(token_client, organizer, event, order, quota, item, subevent):
    with scopes_disabled():
        assert order.positions.count() == 1
    payload = {
        'order': order.code,
        'item': item.pk,
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/'.format(
            organizer.slug, event.slug,
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    assert 'subevent' in str(resp.data)


@pytest.mark.django_db
def test_position_add_quota_empty(token_client, organizer, event, order, quota, item):
    with scopes_disabled():
        assert order.positions.count() == 1
        quota.size = 1
        quota.save()
    payload = {
        'order': order.code,
        'item': item.pk,
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/'.format(
            organizer.slug, event.slug,
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    assert 'quota' in str(resp.data)


@pytest.mark.django_db
def test_position_add_seat(token_client, organizer, event, order, quota, item, seat):
    with scopes_disabled():
        assert order.positions.count() == 1
    payload = {
        'order': order.code,
        'item': item.pk,
        'seat': seat.seat_guid,
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/'.format(
            organizer.slug, event.slug,
        ), format='json', data=payload
    )
    assert resp.status_code == 201
    with scopes_disabled():
        assert order.positions.count() == 2
        op = order.positions.last()
        assert op.item == item
        assert op.price == item.default_price
        assert op.positionid == 3
        assert op.seat == seat


@pytest.mark.django_db
def test_position_add_seat_required(token_client, organizer, event, order, quota, item, seat):
    with scopes_disabled():
        assert order.positions.count() == 1
    payload = {
        'order': order.code,
        'item': item.pk,
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/'.format(
            organizer.slug, event.slug,
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    assert 'seat' in str(resp.data)


@pytest.mark.django_db
def test_position_add_addon_to(token_client, organizer, event, order, quota, item):
    with scopes_disabled():
        cat = event.categories.create(name="Workshops")
        item2 = event.items.create(name="WS1", default_price=23, category=cat)
        quota.items.add(item2)
        item.addons.create(addon_category=cat)
        assert order.positions.count() == 1
    payload = {
        'order': order.code,
        'item': item2.pk,
        'addon_to': 1,
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/'.format(
            organizer.slug, event.slug,
        ), format='json', data=payload
    )
    assert resp.status_code == 201
    with scopes_disabled():
        assert order.positions.count() == 2
        op = order.positions.last()
        assert op.positionid == 3
        assert op.addon_to.positionid == 1


@pytest.mark.django_db
def test_position_add_addon_to_canceled_position(token_client, organizer, event, order, quota, item):
    with scopes_disabled():
        cat = event.categories.create(name="Workshops")
        item2 = event.items.create(name="WS1", default_price=23, category=cat)
        quota.items.add(item2)
        item.addons.create(addon_category=cat)
        assert order.positions.count() == 1
    payload = {
        'order': order.code,
        'item': item2.pk,
        'addon_to': 2,
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/'.format(
            organizer.slug, event.slug,
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    assert 'unknown position' in str(resp.data)


@pytest.mark.django_db
def test_position_add_addon_to_wrong_product(token_client, organizer, event, order, quota, item):
    with scopes_disabled():
        assert order.positions.count() == 1
    payload = {
        'order': order.code,
        'item': item.pk,
        'addon_to': 1,
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/'.format(
            organizer.slug, event.slug,
        ), format='json', data=payload
    )
    assert resp.status_code == 400
    assert 'selected base position does not allow you to add this product as an add-on' in str(resp.data)


@pytest.mark.django_db
def test_position_add_and_set_info(token_client, organizer, event, order, question, quota, item):
    with scopes_disabled():
        assert order.positions.count() == 1
    payload = {
        'order': order.code,
        'item': item.pk,
        'attendee_name': 'John Doe',
        'valid_from': '2022-12-12T12:12:12+00:00',
        'valid_until': '2022-12-12T13:12:12+00:00',
        'answers': [
            {
                'question': question.pk,
                'answer': 'FOOBAR',
            },
        ]
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/'.format(
            organizer.slug, event.slug,
        ), format='json', data=payload
    )
    assert resp.status_code == 201
    with scopes_disabled():
        assert order.positions.count() == 2
        op = order.positions.last()
        assert op.item == item
        assert op.price == item.default_price
        assert op.positionid == 3
        assert op.attendee_name == 'John Doe'
        assert op.answers.count() == 1
        assert op.valid_from.isoformat() == '2022-12-12T12:12:12+00:00'
        assert op.valid_until.isoformat() == '2022-12-12T13:12:12+00:00'


@pytest.mark.django_db
def test_position_update_validity(token_client, organizer, event, order, quota, item, subevent):
    with scopes_disabled():
        op = order.positions.get()
    payload = {
        'valid_from': '2022-12-12T12:12:12+00:00',
        'valid_until': '2022-12-12T13:12:12+00:00',
    }
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
            organizer.slug, event.slug, op.pk
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    op.refresh_from_db()
    assert op.valid_from.isoformat() == '2022-12-12T12:12:12+00:00'
    assert op.valid_until.isoformat() == '2022-12-12T13:12:12+00:00'


@pytest.mark.django_db
def test_order_change_patch(token_client, organizer, event, order, quota):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        quota.items.add(item2)
        p = order.positions.first()
        f = order.fees.first()
    payload = {
        'patch_positions': [
            {
                'position': p.pk,
                'body': {
                    'item': item2.pk,
                    'price': '99.44',
                },
            },
        ],
        'patch_fees': [
            {
                'fee': f.pk,
                'body': {
                    'value': '10.00',
                }
            }
        ]
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    with scopes_disabled():
        p.refresh_from_db()
        assert p.price == Decimal('99.44')
        assert p.item == item2
        f.refresh_from_db()
        assert f.value == Decimal('10.00')
        order.refresh_from_db()
        assert order.total == Decimal('109.44')


@pytest.mark.django_db
def test_order_change_cancel_and_create(token_client, organizer, event, order, quota, item):
    with scopes_disabled():
        p = order.positions.first()
        f = order.fees.first()
        quota.size = 0
        quota.save()
    payload = {
        'cancel_positions': [
            {
                'position': p.pk,
            },
        ],
        'create_positions': [
            {
                'item': item.pk,
                'price': '99.99'
            },
        ],
        'cancel_fees': [
            {
                'fee': f.pk,
            }
        ]
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    with scopes_disabled():
        p.refresh_from_db()
        assert p.canceled
        p_new = order.positions.last()
        assert p_new != p
        assert p_new.item == item
        assert p_new.price == Decimal('99.99')
        f.refresh_from_db()
        assert f.canceled


@pytest.mark.django_db
def test_order_change_send_email_reissue_invoice(token_client, organizer, event, order, quota, item):
    djmail.outbox = []
    with scopes_disabled():
        f = order.fees.first()
        generate_invoice(order)
    payload = {
        'send_email': False,
        'reissue_invoice': True,
        'create_positions': [
            {
                'item': item.pk,
                'price': '99.99'
            },
        ],
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    assert len(djmail.outbox) == 0
    with scopes_disabled():
        assert order.invoices.count() == 3
    payload = {
        'send_email': True,
        'reissue_invoice': False,
        'cancel_fees': [
            {
                'fee': f.pk,
            }
        ]
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    assert len(djmail.outbox) == 1
    with scopes_disabled():
        assert order.invoices.count() == 3


@pytest.mark.django_db
def test_order_change_recalculate_taxes(token_client, organizer, event, order, quota, item):
    djmail.outbox = []
    with scopes_disabled():
        tax_rule = event.tax_rules.create(rate=7)
        p = order.positions.first()
        p.tax_rule = tax_rule
        p.save()
        assert p.tax_rate == 0
    payload = {
        'recalculate_taxes': 'keep_gross',
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert resp.status_code == 200

    with scopes_disabled():
        p.refresh_from_db()
        assert p.tax_rule == tax_rule
        assert p.tax_rate == Decimal('7.00')
        assert p.price == Decimal('23.00')
        assert p.tax_value == Decimal('1.50')

    tax_rule.rate = 10
    tax_rule.save()
    payload = {
        'recalculate_taxes': 'keep_net',
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert resp.status_code == 200

    with scopes_disabled():
        p.refresh_from_db()
        assert p.tax_rule == tax_rule
        assert p.tax_rate == Decimal('10.00')
        assert p.price == Decimal('23.65')
        assert p.tax_value == Decimal('2.15')


@pytest.mark.django_db
def test_order_change_split(token_client, organizer, event, order):
    djmail.outbox = []
    with scopes_disabled():
        p_canceled = order.all_positions.filter(canceled=True).first()
        p_canceled.canceled = False
        p_canceled.save()
        assert event.orders.count() == 1
    payload = {
        'split_positions': [
            {'position': p_canceled.pk}
        ]
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert event.orders.count() == 2


@pytest.mark.django_db
def test_order_change_invalid_input(token_client, organizer, event, order, quota, item, item2):
    djmail.outbox = []
    with scopes_disabled():
        tax_rule = event.tax_rules.create(rate=7)
        p = order.positions.first()
        p_canceled = order.all_positions.filter(canceled=True).first()
        f_canceled = order.all_fees.filter(canceled=True).first()
        p.tax_rule = tax_rule
        p.save()
        assert p.tax_rate == 0
    payload = {
        'cancel_fees': [
            {'fee': f_canceled.pk}
        ]
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert 'does not exist' in str(resp.data)
    assert resp.status_code == 400
    payload = {
        'patch_positions': [
            {'position': p_canceled.pk, 'body': {'price': '99.00'}}
        ],
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert 'does not exist' in str(resp.data)
    assert resp.status_code == 400
    payload = {
        'patch_positions': [
            {'position': p.pk, 'body': {'item': item2.pk}}
        ],
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert 'does not exist' in str(resp.data)
    assert resp.status_code == 400
    payload = {
        'cancel_positions': [
            {'position': p.pk}
        ],
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert 'empty' in str(resp.data)
    assert resp.status_code == 400
    payload = {
        'split_positions': [
            {'position': p.pk}
        ],
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert 'empty' in str(resp.data)
    assert resp.status_code == 400
    payload = {
        'patch_positions': [
            {'position': p.pk, 'body': {}},
            {'position': p.pk, 'body': {}},
        ],
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert 'twice' in str(resp.data)
    assert resp.status_code == 400


@pytest.mark.django_db
def test_order_change_create_addon(token_client, organizer, event, order, quota, item):
    with scopes_disabled():
        cat = event.categories.create(name="Workshops")
        item2 = event.items.create(name="WS1", default_price=23, category=cat)
        quota.items.add(item2)
        item.addons.create(addon_category=cat)
        assert order.positions.count() == 1
    payload = {
        'create_positions': [
            {
                'item': item2.pk,
                'addon_to': 1,
            },
        ],
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/change/'.format(
            organizer.slug, event.slug, order.code,
        ), format='json', data=payload
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert order.positions.count() == 2
        op = order.positions.last()
        assert op.positionid == 3
        assert op.addon_to.positionid == 1
