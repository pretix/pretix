from datetime import datetime
from decimal import Decimal
from unittest import mock

import pytest
from pytz import UTC

from pretix.base.models import InvoiceAddress, Order, OrderPosition


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def order(event, item):
    testtime = datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, secret="k24fiuwvu8kxz3y1",
            datetime=datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC),
            expires=datetime(2017, 12, 10, 10, 0, 0, tzinfo=UTC),
            total=23, payment_provider='banktransfer', locale='en'
        )
        InvoiceAddress.objects.create(order=o, company="Sample company")
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
    "downloads": []
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
        "country": "",
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


@pytest.mark.django_db
def test_orderposition_list(token_client, organizer, event, order, item):
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

    order.positions.first().checkins.create(datetime=datetime(2017, 12, 26, 10, 0, 0, tzinfo=UTC))
    res['checkins'] = [{'datetime': '2017-12-26T10:00:00Z'}]
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?has_checkin=true'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_orderposition_detail(token_client, organizer, event, order, item):
    res = dict(TEST_ORDERPOSITION_RES)
    res["id"] = order.positions.first().pk
    res["item"] = item.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(organizer.slug, event.slug,
                                                                                        order.positions.first().pk))
    assert resp.status_code == 200
    assert res == resp.data
