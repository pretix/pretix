import datetime
from decimal import Decimal
from unittest import mock

import pytest
from django_countries.fields import Country
from pytz import UTC

from pretix.base.models import InvoiceAddress, Order, OrderPosition
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice,
)


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def order(event, item):
    testtime = datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, secret="k24fiuwvu8kxz3y1",
            datetime=datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC),
            expires=datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=UTC),
            total=23, payment_provider='banktransfer', locale='en'
        )
        InvoiceAddress.objects.create(order=o, company="Sample company", country=Country('NZ'))
        OrderPosition.objects.create(
            order=o,
            item=item,
            variation=None,
            price=Decimal("23"),
            attendee_name="Peter",
            secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w"
        )
        return o


TEST_ORDERPOSITION_RES = {
    "id": 1,
    "order": "FOO",
    "positionid": 1,
    "item": 1,
    "variation": None,
    "price": "23.00",
    "attendee_name": "Peter",
    "attendee_email": None,
    "voucher": None,
    "tax_rate": "0.00",
    "tax_value": "0.00",
    "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
    "addon_to": None,
    "checkins": [],
    "downloads": [],
    "answers": [],
    "subevent": None
}
TEST_ORDER_RES = {
    "code": "FOO",
    "status": "n",
    "secret": "k24fiuwvu8kxz3y1",
    "email": "dummy@dummy.test",
    "locale": "en",
    "datetime": "2017-12-01T10:00:00Z",
    "expires": "2017-12-10T10:00:00Z",
    "payment_date": None,
    "payment_provider": "banktransfer",
    "payment_fee": "0.00",
    "payment_fee_tax_rate": "0.00",
    "payment_fee_tax_value": "0.00",
    "total": "23.00",
    "comment": "",
    "invoice_address": {
        "last_modified": "2017-12-01T10:00:00Z",
        "company": "Sample company",
        "name": "",
        "street": "",
        "zipcode": "",
        "city": "",
        "country": "NZ",
        "vat_id": ""
    },
    "positions": [TEST_ORDERPOSITION_RES],
    "downloads": []
}


@pytest.mark.django_db
def test_order_list(token_client, organizer, event, order, item):
    res = dict(TEST_ORDER_RES)
    res["positions"][0]["id"] = order.positions.first().pk
    res["positions"][0]["item"] = item.pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?code=FOO'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?code=BAR'.format(organizer.slug, event.slug))
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


@pytest.mark.django_db
def test_order_detail(token_client, organizer, event, order, item):
    res = dict(TEST_ORDER_RES)
    res["positions"][0]["id"] = order.positions.first().pk
    res["positions"][0]["item"] = item.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/'.format(organizer.slug, event.slug,
                                                                                order.code))
    assert resp.status_code == 200
    assert res == resp.data

    order.status = 'p'
    order.save()
    event.settings.ticketoutput_pdf__enabled = True
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/'.format(organizer.slug, event.slug,
                                                                                order.code))
    assert len(resp.data['downloads']) == 1
    assert len(resp.data['positions'][0]['downloads']) == 1


@pytest.mark.django_db
def test_orderposition_list(token_client, organizer, event, order, item, subevent):
    var = item.variations.create(value="Children")
    res = dict(TEST_ORDERPOSITION_RES)
    op = order.positions.first()
    op.variation = var
    op.save()
    res["id"] = op.pk
    res["item"] = item.pk
    res["variation"] = var.pk

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
        '/api/v1/organizers/{}/events/{}/orderpositions/?item={}'.format(organizer.slug, event.slug, item.pk + 1))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?variation={}'.format(organizer.slug, event.slug, var.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?variation={}'.format(organizer.slug, event.slug, var.pk + 1))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?attendee_name=Peter'.format(organizer.slug, event.slug))
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

    op.checkins.create(datetime=datetime.datetime(2017, 12, 26, 10, 0, 0, tzinfo=UTC))
    res['checkins'] = [{'datetime': '2017-12-26T10:00:00Z'}]
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
        '/api/v1/organizers/{}/events/{}/orderpositions/?subevent={}'.format(organizer.slug, event.slug,
                                                                             subevent.pk + 1))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_orderposition_detail(token_client, organizer, event, order, item):
    res = dict(TEST_ORDERPOSITION_RES)
    op = order.positions.first()
    res["id"] = op.pk
    res["item"] = item.pk
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


@pytest.fixture
def invoice(order):
    testtime = datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        return generate_invoice(order)


TEST_INVOICE_RES = {
    "order": "FOO",
    "number": "DUMMY-00001",
    "is_cancellation": False,
    "invoice_from": "",
    "invoice_to": "Sample company\n\n\n \nNew Zealand",
    "date": "2017-12-10",
    "refers": None,
    "locale": "en",
    "introductory_text": "",
    "additional_text": "",
    "payment_provider_text": "",
    "footer_text": "",
    "lines": [
        {
            "description": "Budget Ticket",
            "gross_value": "23.00",
            "tax_value": "0.00",
            "tax_rate": "0.00"
        }
    ]
}


@pytest.mark.django_db
def test_invoice_list(token_client, organizer, event, order, invoice):
    res = dict(TEST_INVOICE_RES)

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
def test_invoice_detail(token_client, organizer, event, invoice):
    res = dict(TEST_INVOICE_RES)

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/{}/'.format(organizer.slug, event.slug,
                                                                                  invoice.number))
    assert resp.status_code == 200
    assert res == resp.data
