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
from datetime import datetime, timezone
from decimal import Decimal
from unittest import mock

import pytest
from django_countries.fields import Country
from django_scopes import scopes_disabled

from pretix.base.models import (
    InvoiceAddress, Order, OrderPosition, SeatingPlan, SubEvent,
)
from pretix.base.models.orders import OrderFee


@pytest.fixture
def variations(item):
    v = []
    v.append(item.variations.create(value="ChildA1", default_price='12.00'))
    v.append(item.variations.create(value="ChildA2", default_price='13.00'))
    return v


@pytest.fixture
def variations2(item2):
    v = []
    v.append(item2.variations.create(value="ChildB1", default_price='12.00'))
    v.append(item2.variations.create(value="ChildB2", default_price='13.00'))
    return v


@pytest.fixture
def order(event, item, taxrule):
    testtime = datetime(2017, 12, 1, 10, 0, 0, tzinfo=timezone.utc)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, secret="k24fiuwvu8kxz3y1",
            datetime=datetime(2017, 12, 1, 10, 0, 0, tzinfo=timezone.utc),
            expires=datetime(2017, 12, 10, 10, 0, 0, tzinfo=timezone.utc),
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
    'frontpage_text': None,
    'date_from': '2017-12-27T10:00:00Z',
    'presale_end': None,
    'seating_plan': None,
    "seat_category_mapping": {},
    'id': 1,
    'variation_price_overrides': [],
    'location': None,
    "geo_lat": None,
    "geo_lon": None,
    'is_public': True,
    'item_price_overrides': [],
    'meta_data': {'type': 'Workshop'}
}


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def item2(event2):
    return event2.items.create(name="Another Ticket", default_price=23)


@pytest.mark.django_db
def test_subevent_list(token_client, organizer, event, subevent):
    res = dict(TEST_SUBEVENT_RES)
    res["id"] = subevent.pk
    res["last_modified"] = subevent.last_modified.isoformat().replace('+00:00', 'Z')
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

    resp = token_client.get('/api/v1/organizers/{}/events/?with_availability_for=web'.format(organizer.slug))
    assert resp.status_code == 200
    assert resp.data['results'][0]['best_availability_state'] is None


@pytest.mark.django_db
def test_subevent_list_filter(token_client, organizer, event, subevent):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/subevents/?attr[type]=Workshop'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert resp.data['count'] == 1

    resp = token_client.get('/api/v1/organizers/{}/events/{}/subevents/?attr[type]=Conference'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert resp.data['count'] == 0

    resp = token_client.get('/api/v1/organizers/{}/events/{}/subevents/?search=Foobar'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert resp.data['count'] == 1

    resp = token_client.get('/api/v1/organizers/{}/events/{}/subevents/?search=Barfoo'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert resp.data['count'] == 0

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/subevents/?date_from_after=2017-12-27T10:00:00Z'.format(
            organizer.slug, event.slug
        )
    )
    assert resp.status_code == 200
    assert resp.data['count'] == 1

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/subevents/?date_from_after=2017-12-27T10:00:01Z'.format(
            organizer.slug, event.slug
        )
    )
    assert resp.status_code == 200
    assert resp.data['count'] == 0

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/subevents/?date_from_before=2017-12-27T10:00:00Z'.format(
            organizer.slug, event.slug
        )
    )
    assert resp.status_code == 200
    assert resp.data['count'] == 1

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/subevents/?date_from_before=2017-12-27T09:59:00Z'.format(
            organizer.slug, event.slug
        )
    )
    assert resp.status_code == 200
    assert resp.data['count'] == 0


@pytest.mark.django_db
def test_subevent_create(team, token_client, organizer, event, subevent, meta_prop, item):
    meta_prop.allowed_values = "Conference\nWorkshop"
    meta_prop.save()
    team.can_change_organizer_settings = False
    team.save()
    organizer.meta_properties.create(
        name="protected", protected=True
    )
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
                "type": "Workshop",
                "protected": "ignored",
            },
        },
        format='json'
    )
    assert resp.status_code == 201
    assert not subevent.active
    with scopes_disabled():
        assert subevent.meta_values.filter(
            property__name=meta_prop.name, value="Workshop"
        ).exists()
        assert not subevent.meta_values.filter(
            property__name="ignored",
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
            "item_price_overrides": [],
            "variation_price_overrides": [],
            "meta_data": {
                meta_prop.name: "bar"
            },
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"meta_data":["Meta data property \'type\' does not allow value \'bar\'."]}'

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
    assert item.default_price == Decimal('23.00')
    with scopes_disabled():
        assert event.subevents.get(id=resp.data['id']).item_price_overrides[item.pk] == Decimal('23.42')

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
def test_subevent_update(token_client, organizer, event, subevent, item, item2, meta_prop, variations, variations2):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "date_from": "2018-12-27T10:00:00Z",
            "date_to": "2018-12-28T10:00:00Z",
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        subevent = event.subevents.get(id=subevent.id)
    assert subevent.date_from == datetime(2018, 12, 27, 10, 0, tzinfo=timezone.utc)
    assert subevent.date_to == datetime(2018, 12, 28, 10, 0, tzinfo=timezone.utc)

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
    with scopes_disabled():
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
    with scopes_disabled():
        assert not subevent.meta_values.filter(
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
    with scopes_disabled():
        assert subevent.items.get(id=item.pk).default_price == Decimal('23.00')
    assert subevent.item_price_overrides[item.pk] == Decimal('99.99')

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "item_price_overrides": [
                {
                    "item": item.pk,
                    "price": "88.88"
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert event.subevents.get(id=subevent.id).item_price_overrides[item.pk] == Decimal('88.88')

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "item_price_overrides": [
                {
                    "item": item.pk,
                    "price": None
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert item.pk not in event.subevents.get(id=subevent.id).item_price_overrides

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "item_price_overrides": [
                {
                    "item": item.pk,
                    "price": "12.34"
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert event.subevents.get(id=subevent.id).item_price_overrides[item.pk] == Decimal('12.34')

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "item_price_overrides": [],
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert item.pk not in event.subevents.get(id=subevent.id).item_price_overrides

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

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "item_price_overrides": [
                {
                    "item": item2.id,
                    "price": "99.99"
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["One or more items do not belong to this event."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "variation_price_overrides": [
                {
                    "variation": variations[0].pk,
                    "price": "99.99"
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert subevent.variations.get(id=variations[0].pk).default_price == Decimal('12.00')
        assert subevent.var_price_overrides[variations[0].pk] == Decimal('99.99')

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "variation_price_overrides": [
                {
                    "variation": variations[0].pk,
                    "price": "88.88"
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert event.subevents.get(id=subevent.id).var_price_overrides[variations[0].pk] == Decimal('88.88')

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "variation_price_overrides": [
                {
                    "variation": variations[0].pk,
                    "price": None
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert variations[0].pk not in event.subevents.get(id=subevent.id).var_price_overrides

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "variation_price_overrides": [
                {
                    "variation": variations[0].pk,
                    "price": "12.34"
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert event.subevents.get(id=subevent.id).var_price_overrides[variations[0].pk] == Decimal('12.34')

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "variation_price_overrides": [],
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert variations[0].pk not in event.subevents.get(id=subevent.id).var_price_overrides

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "variation_price_overrides": [
                {
                    "variation": 123,
                    "price": "99.99"
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"variation_price_overrides":[{"variation":["Invalid pk \\"123\\" - object does not exist."]}]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "variation_price_overrides": [
                {
                    "variation": variations2[0].pk,
                    "price": "99.99"
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["One or more variations do not belong to this event."]}'


@pytest.mark.django_db
def test_subevent_update_keep_subeventitems(token_client, organizer, event, subevent, item, item2):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "item_price_overrides": [
                {
                    "item": item.pk,
                    "price": "88.88",
                    "disabled": True
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert event.subevents.get(id=subevent.id).item_overrides[item.pk].disabled

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "date_from": "2017-12-27T10:00:00Z",
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert event.subevents.get(id=subevent.id).item_overrides[item.pk].disabled


@pytest.mark.django_db
def test_subevent_detail(token_client, organizer, event, subevent):
    res = dict(TEST_SUBEVENT_RES)
    res["id"] = subevent.pk
    res["last_modified"] = subevent.last_modified.isoformat().replace('+00:00', 'Z')
    resp = token_client.get('/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug,
                                                                                   subevent.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_subevent_delete(token_client, organizer, event, subevent):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug,
                                                                                      subevent.pk))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not event.subevents.filter(pk=subevent.id).exists()


@pytest.mark.django_db
def test_subevent_with_order_position_not_delete(token_client, organizer, event, subevent, item, order_position):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug,
                                                                                      subevent.pk))
    assert resp.status_code == 403
    assert resp.content.decode() == '{"detail":"The sub-event can not be deleted as it has already been used in ' \
                                    'orders. Please set \'active\' to false instead to hide it from users."}'
    with scopes_disabled():
        assert event.subevents.filter(pk=subevent.id).exists()


@pytest.fixture
def seatingplan(event, organizer, item):
    return SeatingPlan.objects.create(
        name="Plan", organizer=organizer, layout="""{
  "name": "Grosser Saal",
  "categories": [
    {
      "name": "Stalls",
      "color": "red"
    }
  ],
  "zones": [
    {
      "name": "Main Area",
      "position": {
        "x": 0,
        "y": 0
      },
      "rows": [
        {
          "row_number": "0",
          "seats": [
            {
              "seat_guid": "0-0",
              "seat_number": "0-0",
              "position": {
                "x": 0,
                "y": 0
              },
              "category": "Stalls"
            },
            {
              "seat_guid": "0-1",
              "seat_number": "0-1",
              "position": {
                "x": 33,
                "y": 0
              },
              "category": "Stalls"
            },
            {
              "seat_guid": "0-2",
              "seat_number": "0-2",
              "position": {
                "x": 66,
                "y": 0
              },
              "category": "Stalls"
            }
          ],
          "position": {
            "x": 0,
            "y": 0
          }
        }
      ]
    }
  ],
  "size": {
    "width": 600,
    "height": 400
  }
}"""
    )


@pytest.mark.django_db
def test_subevent_update_seating(token_client, organizer, event, item, subevent, seatingplan):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    subevent.refresh_from_db()
    assert subevent.seating_plan == seatingplan
    with scopes_disabled():
        assert subevent.seats.count() == 3
        assert subevent.seats.filter(product=item).count() == 3
        m = subevent.seat_category_mappings.get()
    assert m.layout_category == 'Stalls'
    assert m.product == item


@pytest.mark.django_db
def test_subevent_update_seating_invalid_product(token_client, organizer, event, item, seatingplan, subevent):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk + 2
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"seat_category_mapping":["Item \'%d\' does not exist."]}' % (item.pk + 2)


@pytest.mark.django_db
def test_subevent_update_seating_change_mapping(token_client, organizer, event, item, seatingplan, subevent):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    subevent.refresh_from_db()
    assert subevent.seating_plan == seatingplan
    with scopes_disabled():
        assert subevent.seats.count() == 3
        assert subevent.seats.filter(product=item).count() == 3
        m = subevent.seat_category_mappings.get()
    assert m.layout_category == 'Stalls'
    assert m.product == item

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "seat_category_mapping": {
                "VIP": item.pk,
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    subevent.refresh_from_db()
    assert subevent.seating_plan == seatingplan
    with scopes_disabled():
        assert subevent.seats.count() == 3
        m = subevent.seat_category_mappings.get()
        assert subevent.seats.filter(product=None).count() == 3
    assert m.layout_category == 'VIP'
    assert m.product == item


@pytest.mark.django_db
def test_remove_seating(token_client, organizer, event, item, seatingplan, subevent):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    subevent.refresh_from_db()
    assert subevent.seating_plan == seatingplan
    with scopes_disabled():
        assert subevent.seats.count() == 3
        assert subevent.seat_category_mappings.count() == 1

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "seating_plan": None
        },
        format='json'
    )
    assert resp.status_code == 200
    subevent.refresh_from_db()
    assert subevent.seating_plan is None
    with scopes_disabled():
        assert subevent.seats.count() == 0
        assert subevent.seat_category_mappings.count() == 0


@pytest.mark.django_db
def test_remove_seating_forbidden(token_client, organizer, event, item, seatingplan, order_position, subevent):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    subevent.refresh_from_db()
    assert subevent.seating_plan == seatingplan
    with scopes_disabled():
        assert subevent.seats.count() == 3
        assert subevent.seat_category_mappings.count() == 1

        order_position.seat = subevent.seats.first()
        order_position.save()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug, subevent.pk),
        {
            "seating_plan": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"seating_plan":["You can not change the plan since seat \\"0-0\\" is not ' \
                                    'present in the new plan and is already sold."]}'


@pytest.mark.django_db
def test_subevent_create_with_seating(token_client, organizer, event, subevent, item, seatingplan):
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
            "seat_category_mapping": {
                "Stalls": item.pk
            },
            "meta_data": {},
            "seating_plan": seatingplan.pk,
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        subevent = SubEvent.objects.get(pk=resp.data['id'])
        assert subevent.seats.count() == 3
        assert subevent.seat_category_mappings.count() == 1
