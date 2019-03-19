from datetime import datetime
from decimal import Decimal
from unittest import mock

import pytest
from django_countries.fields import Country
from pytz import UTC

from pretix.base.models import Event, InvoiceAddress, Order, OrderPosition
from pretix.base.models.orders import OrderFee


@pytest.fixture
def variations(item):
    v = list()
    v.append(item.variations.create(value="ChildA1"))
    v.append(item.variations.create(value="ChildA2"))
    return v


@pytest.fixture
def order(event, item, taxrule):
    testtime = datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, secret="k24fiuwvu8kxz3y1",
            datetime=datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC),
            expires=datetime(2017, 12, 10, 10, 0, 0, tzinfo=UTC),
            total=23, locale='en'
        )
        o.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.25'), tax_rate=Decimal('19.00'),
                      tax_value=Decimal('0.05'), tax_rule=taxrule)
        InvoiceAddress.objects.create(order=o, company="Sample company", country=Country('NZ'))
        return o


@pytest.fixture
def order_position(item, order, subevent, taxrule, variations):
    op = OrderPosition.objects.create(
        order=order,
        item=item,
        subevent=subevent,
        variation=variations[0],
        tax_rule=taxrule,
        tax_rate=taxrule.rate,
        tax_value=Decimal("3"),
        price=Decimal("23"),
        attendee_name_parts={'full_name': "Peter"},
        secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w"
    )
    return op


TEST_SUBEVENT_RES = {
    'active': False,
    'event': 'dummy',
    'presale_start': None,
    'date_to': None,
    'date_admission': None,
    'name': {'en': 'Foobar'},
    'date_from': '2017-12-27T10:00:00Z',
    'presale_end': None,
    'id': 1,
    'variation_price_overrides': [],
    'location': None,
    'item_price_overrides': [],
    'meta_data': {'type': 'Workshop'}
}


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.mark.django_db
def test_subevent_list(token_client, organizer, event, subevent):
    res = dict(TEST_SUBEVENT_RES)
    res["id"] = subevent.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/subevents/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/subevents/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/subevents/?active=false'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/subevents/?active=true'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/subevents/?event__live=false'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/subevents/?event__live=true'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/subevents/?ends_after=2017-12-27T09:59:59Z'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/subevents/?ends_after=2017-12-27T10:01:01Z'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_subevent_get(token_client, organizer, event, subevent):
    res = dict(TEST_SUBEVENT_RES)
    res["id"] = subevent.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug,
                                                                                   subevent.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_subevent_create(token_client, organizer, event, subevent, meta_prop, item):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/subevents/'.format(organizer.slug, event.slug),
        {
            "name": {
                "de": "Demo Subevent 2020 Test",
                "en": "Demo Subevent 2020 Test"
            },
            "active": False,
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "item_price_overrides": [],
            "variation_price_overrides": [],
            "meta_data": {
                "type": "Workshop"
            },
        },
        format='json'
    )
    assert resp.status_code == 201
    assert not organizer.events.get(slug="dummy").subevents.get(id=resp.data['id']).active
    assert organizer.events.get(slug="dummy").subevents.get(id=resp.data['id']).meta_values.filter(
        property__name=meta_prop.name, value="Workshop"
    ).exists()

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/subevents/'.format(organizer.slug, event.slug),
        {
            "name": {
                "de": "Demo Subevent 2020 Test",
                "en": "Demo Subevent 2020 Test"
            },
            "active": False,
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "item_price_overrides": [],
            "variation_price_overrides": [],
            "meta_data": {
                "foo": "bar"
            },
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"meta_data":["Meta data property \'foo\' does not exist."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/subevents/'.format(organizer.slug, event.slug),
        {
            "name": {
                "de": "Demo Subevent 2020 Test",
                "en": "Demo Subevent 2020 Test"
            },
            "active": False,
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "item_price_overrides": [
                {
                    "item": item.pk,
                    "price": "23.42"
                }
            ],
            "variation_price_overrides": [],
            "meta_data": {
                "type": "Workshop"
            },
        },
        format='json'
    )
    assert resp.status_code == 201
    assert organizer.events.get(slug="dummy").subevents.get(id=resp.data['id']).items.get(id=item.pk).default_price == Decimal('23.00')
    assert organizer.events.get(slug="dummy").subevents.get(id=resp.data['id']).item_price_overrides[item.pk] == Decimal('23.42')

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/subevents/'.format(organizer.slug, event.slug),
        {
            "name": {
                "de": "Demo Subevent 2020 Test",
                "en": "Demo Subevent 2020 Test"
            },
            "active": False,
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "item_price_overrides": [
                {
                    "item": 555,
                    "price": "23.42"
                }
            ],
            "variation_price_overrides": [],
            "meta_data": {
                "type": "Workshop"
            },
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"item_price_overrides":[{"item":["Invalid pk \\"555\\" - object does not exist."]}]}'


@pytest.mark.django_db
def test_subevent_update(token_client, organizer, event, subevent, item, meta_prop):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "date_from": "2018-12-27T10:00:00Z",
            "date_to": "2018-12-28T10:00:00Z",
        },
        format='json'
    )
    assert resp.status_code == 200
    event = Event.objects.get(organizer=organizer.pk, slug=event.slug)
    assert organizer.events.get(slug=event.slug).subevents.get(id=resp.data['id']).meta_values.filter(
        property__name=meta_prop.name, value="Workshop"
    ).exists()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-26T10:00:00Z"
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The event cannot end before it starts."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "presale_start": "2017-12-27T10:00:00Z",
            "presale_end": "2017-12-26T10:00:00Z"
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The event\'s presale cannot end before it starts."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "meta_data": {
                meta_prop.name: "Conference"
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    assert organizer.events.get(slug=event.slug).subevents.get(id=resp.data['id']).meta_values.filter(
        property__name=meta_prop.name, value="Conference"
    ).exists()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "meta_data": {
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    assert not organizer.events.get(slug=event.slug).subevents.get(id=resp.data['id']).meta_values.filter(
        property__name=meta_prop.name
    ).exists()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "meta_data": {
                "test": "test"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"meta_data":["Meta data property \'test\' does not exist."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "item_price_overrides": [
                {
                    "item": item.pk,
                    "price": "99.99"
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 200
    assert organizer.events.get(slug="dummy").subevents.get(id=resp.data['id']).items.get(id=item.pk).default_price == Decimal('23.00')
    assert organizer.events.get(slug="dummy").subevents.get(id=resp.data['id']).item_price_overrides[item.pk] == Decimal('99.99')

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "item_price_overrides": [
                {
                    "item": 123,
                    "price": "99.99"
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"item_price_overrides":[{"item":["Invalid pk \\"123\\" - object does not exist."]}]}'


@pytest.mark.django_db
def test_subevent_detail(token_client, organizer, event, subevent):
    res = dict(TEST_SUBEVENT_RES)
    res["id"] = subevent.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug,
                                                                                   subevent.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_subevent_delete(token_client, organizer, event, subevent):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug,
                                                                                      subevent.pk))
    assert resp.status_code == 204
    assert not organizer.events.get(pk=event.id).subevents.filter(pk=subevent.id).exists()


@pytest.mark.django_db
def test_subevent_with_order_position_not_delete(token_client, organizer, event, subevent, item, order_position):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug,
                                                                                      subevent.pk))
    assert resp.status_code == 403
    assert resp.content.decode() == '{"detail":"The sub-event can not be deleted as it has already been used in ' \
                                    'orders. Please set \'active\' to false instead to hide it from users."}'
    assert organizer.events.get(pk=event.id).subevents.filter(pk=subevent.id).exists()
