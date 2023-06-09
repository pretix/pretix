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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze, Ture Gjørup, pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import mock

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.timezone import now
from django_countries.fields import Country
from django_scopes import scopes_disabled
from tests.const import SAMPLE_PNG

from pretix.base.models import (
    Event, InvoiceAddress, Order, OrderPosition, Organizer, SeatingPlan,
)
from pretix.base.models.orders import OrderFee
from pretix.testutils.mock import mocker_context


@pytest.fixture
def variations(item):
    v = []
    v.append(item.variations.create(value="ChildA1"))
    v.append(item.variations.create(value="ChildA2"))
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
def order_position(item, order, taxrule, variations):
    op = OrderPosition.objects.create(
        order=order,
        item=item,
        variation=variations[0],
        tax_rule=taxrule,
        tax_rate=taxrule.rate,
        tax_value=Decimal("3"),
        price=Decimal("23"),
        attendee_name_parts={'full_name': "Peter"},
        secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w"
    )
    return op


TEST_EVENT_RES = {
    "name": {"en": "Dummy"},
    "live": False,
    "testmode": False,
    "currency": "EUR",
    "date_from": "2017-12-27T10:00:00Z",
    "date_to": None,
    "date_admission": None,
    "is_public": True,
    "presale_start": None,
    "presale_end": None,
    "location": None,
    "geo_lat": None,
    "geo_lon": None,
    "slug": "dummy",
    "has_subevents": False,
    "seating_plan": None,
    "seat_category_mapping": {},
    "meta_data": {"type": "Conference"},
    'timezone': 'Europe/Berlin',
    'plugins': [
        'pretix.plugins.banktransfer',
        'pretix.plugins.ticketoutputpdf'
    ],
    'item_meta_properties': {
        'day': 'Monday',
    },
    'sales_channels': ['web', 'bar', 'baz'],
    'public_url': 'http://example.com/dummy/dummy/'
}


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def free_item(event):
    return event.items.create(name="Free Ticket", default_price=0)


@pytest.fixture
def free_quota(event, free_item):
    q = event.quotas.create(name="Budget Quota", size=200)
    q.items.add(free_item)
    return q


@pytest.mark.django_db
def test_event_list(token_client, organizer, event):
    resp = token_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert resp.status_code == 200
    assert TEST_EVENT_RES == resp.data['results'][0]

    resp = token_client.get('/api/v1/organizers/{}/events/?live=true'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/?live=false'.format(organizer.slug))
    assert resp.status_code == 200
    assert [TEST_EVENT_RES] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/?testmode=true'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/?testmode=false'.format(organizer.slug))
    assert resp.status_code == 200
    assert [TEST_EVENT_RES] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/?is_public=false'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/?is_public=true'.format(organizer.slug))
    assert resp.status_code == 200
    assert [TEST_EVENT_RES] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/?has_subevents=true'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/?has_subevents=false'.format(organizer.slug))
    assert resp.status_code == 200
    assert [TEST_EVENT_RES] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/?ends_after=2017-12-27T10:01:00Z'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/?ends_after=2017-12-27T09:59:59Z'.format(organizer.slug))
    assert resp.status_code == 200
    assert [TEST_EVENT_RES] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/?with_availability_for=web'.format(organizer.slug))
    assert resp.status_code == 200
    assert resp.data['results'][0]['best_availability_state'] is None


@pytest.mark.django_db
def test_event_list_filter(token_client, organizer, event):
    resp = token_client.get('/api/v1/organizers/{}/events/?attr[type]=Conference'.format(organizer.slug))
    assert resp.status_code == 200
    assert resp.data['count'] == 1

    resp = token_client.get('/api/v1/organizers/{}/events/?attr[type]='.format(organizer.slug))
    assert resp.status_code == 200
    assert resp.data['count'] == 0

    resp = token_client.get('/api/v1/organizers/{}/events/?date_from_after=2017-12-27T10:00:00Z'.format(organizer.slug))
    assert resp.status_code == 200
    assert resp.data['count'] == 1

    resp = token_client.get('/api/v1/organizers/{}/events/?date_from_after=2017-12-27T10:00:01Z'.format(organizer.slug))
    assert resp.status_code == 200
    assert resp.data['count'] == 0


@pytest.mark.django_db
def test_event_list_name_filter(token_client, organizer, event):
    resp = token_client.get('/api/v1/organizers/{}/events/?search=Dummy'.format(organizer.slug))
    assert resp.status_code == 200
    assert resp.data['count'] == 1

    resp = token_client.get('/api/v1/organizers/{}/events/?search=notdummy'.format(organizer.slug))
    assert resp.status_code == 200
    assert resp.data['count'] == 0


@pytest.mark.django_db
def test_event_get(token_client, organizer, event):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug))
    res = copy.copy(TEST_EVENT_RES)
    res["valid_keys"] = {"pretix_sig1": []}
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_event_create(team, token_client, organizer, event, meta_prop):
    meta_prop.allowed_values = "Conference\nWorkshop"
    meta_prop.save()
    team.can_change_organizer_settings = False
    team.save()
    organizer.meta_properties.create(
        name="protected", protected=True
    )
    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2030",
            "meta_data": {
                meta_prop.name: "Conference",
                "protected": "ignored",
            },
            "seat_category_mapping": {},
            "timezone": "Europe/Amsterdam"
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        assert not organizer.events.get(slug="2030").testmode
        assert organizer.events.get(slug="2030").meta_values.filter(
            property__name=meta_prop.name, value="Conference"
        ).exists()
        assert not organizer.events.get(slug="2030").meta_values.filter(
            property__name="protected"
        ).exists()
        assert organizer.events.get(slug="2030").plugins == settings.PRETIX_PLUGINS_DEFAULT
        assert organizer.events.get(slug="2030").settings.timezone == "Europe/Amsterdam"

    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2020",
            "meta_data": {
                "foo": "bar"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"meta_data":["Meta data property \'foo\' does not exist."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2020",
            "meta_data": {
                meta_prop.name: "bar"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"meta_data":["Meta data property \'type\' does not allow value \'bar\'."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": event.slug,
            "meta_data": {
                "type": "Conference"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"slug":["This slug has already been used for a different event."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": True,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2031",
            "meta_data": {
                "type": "Conference"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"live":["Events cannot be created as \'live\'. Quotas and payment must be added ' \
                                    'to the event before sales can go live."]}'


@pytest.mark.django_db
@pytest.mark.parametrize("urlstyle", [
    '/api/v1/organizers/{}/events/{}/clone/',
    '/api/v1/organizers/{}/events/?clone_from={}',
])
def test_event_create_with_clone(token_client, organizer, event, meta_prop, urlstyle):
    event.date_admission = event.date_from - timedelta(hours=1)
    event.save()
    resp = token_client.post(
        urlstyle.format(organizer.slug, event.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "testmode": True,
            "currency": "EUR",
            "date_from": "2018-12-27T10:00:00Z",
            "date_to": "2018-12-28T10:00:00Z",
            "date_admission": "2018-12-27T08:00:00Z",
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2030",
            "meta_data": {
                "type": "Conference"
            },
            "plugins": [
                "pretix.plugins.ticketoutputpdf"
            ],
            "timezone": "Europe/Vienna"
        },
        format='json'
    )

    assert resp.status_code == 201
    with scopes_disabled():
        cloned_event = Event.objects.get(organizer=organizer.pk, slug='2030')
        assert cloned_event.plugins == 'pretix.plugins.ticketoutputpdf'
        assert cloned_event.is_public is False
        assert cloned_event.testmode
        assert cloned_event.date_admission.isoformat() == "2018-12-27T08:00:00+00:00"
        assert organizer.events.get(slug="2030").meta_values.filter(
            property__name=meta_prop.name, value="Conference"
        ).exists()
        assert cloned_event.settings.timezone == "Europe/Vienna"

    resp = token_client.post(
        urlstyle.format(organizer.slug, event.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2018-12-27T10:00:00Z",
            "date_to": "2018-12-28T10:00:00Z",
            "date_admission": None,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2031",
            "meta_data": {
                "type": "Conference"
            }
        },
        format='json'
    )

    assert resp.status_code == 201
    with scopes_disabled():
        cloned_event = Event.objects.get(organizer=organizer.pk, slug='2031')
        assert cloned_event.plugins == event.plugins
        assert cloned_event.is_public is True
        assert organizer.events.get(slug="2031").meta_values.filter(
            property__name=meta_prop.name, value="Conference"
        ).exists()

    resp = token_client.post(
        urlstyle.format(organizer.slug, event.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2018-12-27T10:00:00Z",
            "date_to": "2018-12-28T10:00:00Z",
            "date_admission": None,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2032",
            "plugins": []
        },
        format='json'
    )

    assert resp.status_code == 201
    with scopes_disabled():
        cloned_event = Event.objects.get(organizer=organizer.pk, slug='2032')
        assert cloned_event.plugins == ""


@pytest.mark.django_db
def test_event_create_with_clone_unknown_source(user, user_client, organizer, event):
    with scopes_disabled():
        target_org = Organizer.objects.create(name='Dummy', slug='dummy2')
        target_org.events.create(slug='bar', name='bar', date_from=now())
    resp = user_client.post(
        '/api/v1/organizers/{}/events/?clone_from={}/{}'.format(organizer.slug, 'dummy2', 'bar'),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "testmode": True,
            "currency": "EUR",
            "date_from": "2018-12-27T10:00:00Z",
            "date_to": "2018-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2030",
            "plugins": [
                "pretix.plugins.ticketoutputpdf"
            ],
            "timezone": "Europe/Vienna"
        },
        format='json'
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_event_create_with_clone_across_organizers(user, user_client, organizer, event, taxrule):
    with scopes_disabled():
        target_org = Organizer.objects.create(name='Dummy', slug='dummy2')
        team = target_org.teams.create(
            name="Test-Team",
            can_change_teams=True,
            can_manage_gift_cards=True,
            can_change_items=True,
            can_create_events=True,
            can_change_event_settings=True,
            can_change_vouchers=True,
            can_view_vouchers=True,
            can_change_orders=True,
            can_manage_customers=True,
            can_change_organizer_settings=True
        )
        team.members.add(user)

    resp = user_client.post(
        '/api/v1/organizers/{}/events/?clone_from={}/{}'.format(target_org.slug, organizer.slug, event.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "testmode": True,
            "currency": "EUR",
            "date_from": "2018-12-27T10:00:00Z",
            "date_to": "2018-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2030",
            "plugins": [
                "pretix.plugins.ticketoutputpdf"
            ],
            "timezone": "Europe/Vienna"
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        cloned_event = Event.objects.get(organizer=target_org.pk, slug='2030')
        assert cloned_event.plugins == 'pretix.plugins.ticketoutputpdf'
        assert cloned_event.is_public is False
        assert cloned_event.testmode
        assert cloned_event.settings.timezone == "Europe/Vienna"
        assert cloned_event.tax_rules.exists()


@pytest.mark.django_db
def test_event_put_with_clone(token_client, organizer, event, meta_prop):
    resp = token_client.put(
        '/api/v1/organizers/{}/events/{}/clone/'.format(organizer.slug, event.slug),
        {},
        format='json'
    )

    assert resp.status_code == 405


@pytest.mark.django_db
def test_event_patch_with_clone(token_client, organizer, event, meta_prop):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/clone/'.format(organizer.slug, event.slug),
        {},
        format='json'
    )

    assert resp.status_code == 405


@pytest.mark.django_db
def test_event_delete_with_clone(token_client, organizer, event, meta_prop):
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/clone/'.format(organizer.slug, event.slug),
        {},
        format='json'
    )

    assert resp.status_code == 405


@pytest.mark.django_db
def test_event_update(token_client, organizer, event, item, meta_prop):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "date_from": "2018-12-27T10:00:00Z",
            "date_to": "2018-12-28T10:00:00Z",
            "currency": "DKK",
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(organizer=organizer.pk, slug=resp.data['slug'])
        assert event.currency == "DKK"
        assert organizer.events.get(slug=resp.data['slug']).meta_values.filter(
            property__name=meta_prop.name, value="Conference"
        ).exists()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-26T10:00:00Z"
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The event cannot end before it starts."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "presale_start": "2017-12-27T10:00:00Z",
            "presale_end": "2017-12-26T10:00:00Z"
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The event\'s presale cannot end before it starts."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "slug": "testing"
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"slug":["The event slug cannot be changed."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "has_subevents": True
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"has_subevents":["Once created an event cannot change between an series and a ' \
                                    'single event."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "meta_data": {
                meta_prop.name: "Workshop"
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert organizer.events.get(slug=resp.data['slug']).meta_values.filter(
            property__name=meta_prop.name, value="Workshop"
        ).exists()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "meta_data": {
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert not organizer.events.get(slug=resp.data['slug']).meta_values.filter(
            property__name=meta_prop.name
        ).exists()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
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
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "item_meta_properties": {
                "Foo": "Bar"
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert organizer.events.get(slug=resp.data['slug']).item_meta_properties.filter(
            name="Foo", default="Bar"
        ).exists()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "item_meta_properties": {
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert not organizer.events.get(slug=resp.data['slug']).item_meta_properties.filter(
            name="Foo"
        ).exists()


@pytest.mark.django_db
def test_event_test_mode(token_client, organizer, event):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "testmode": True
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.testmode
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "testmode": False
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert not event.testmode


@pytest.mark.django_db
def test_event_update_live_no_product(token_client, organizer, event):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "live": True
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"live":["You need to configure at least one quota to sell anything."]}'


@pytest.mark.django_db
def test_event_update_live_no_payment_method(token_client, organizer, event, item, free_quota):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "live": True
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"live":["You have configured at least one paid product but have not enabled any ' \
                                    'payment methods."]}'


@pytest.mark.django_db
def test_event_update_live_free_product(token_client, organizer, event, free_item, free_quota):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "live": True
        },
        format='json'
    )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_event_update_plugins(token_client, organizer, event, free_item, free_quota):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "plugins": [
                "pretix.plugins.ticketoutputpdf",
            ]
        },
        format='json'
    )
    assert resp.status_code == 200
    assert set(resp.data.get('plugins')) == {
        "pretix.plugins.ticketoutputpdf",
    }

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "plugins": {
                "pretix.plugins.banktransfer"
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data.get('plugins') == [
        "pretix.plugins.banktransfer"
    ]

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "plugins": {
                "pretix.plugins.test"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"plugins":["Unknown plugin: \'pretix.plugins.test\'."]}'


@pytest.mark.django_db
def test_event_delete(token_client, organizer, event):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not organizer.events.filter(pk=event.id).exists()


@pytest.mark.django_db
def test_event_with_order_position_not_delete(token_client, organizer, event, item, order_position):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug))
    assert resp.status_code == 403
    assert resp.content.decode() == '{"detail":"The event can not be deleted as it already contains orders. Please ' \
                                    'set \'live\' to false to hide the event and take the shop offline instead."}'
    with scopes_disabled():
        assert organizer.events.filter(pk=event.id).exists()


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
def test_event_update_seating(token_client, organizer, event, item, seatingplan):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan == seatingplan
    with scopes_disabled():
        assert event.seats.count() == 3
        assert event.seats.filter(product=item).count() == 3
        m = event.seat_category_mappings.get()
    assert m.layout_category == 'Stalls'
    assert m.product == item


@pytest.mark.django_db
def test_event_update_seating_invalid_product(token_client, organizer, event, item, seatingplan):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
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
def test_event_update_seating_change_mapping(token_client, organizer, event, item, seatingplan):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan == seatingplan
    with scopes_disabled():
        assert event.seats.count() == 3
        assert event.seats.filter(product=item).count() == 3
        m = event.seat_category_mappings.get()
    assert m.layout_category == 'Stalls'
    assert m.product == item

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seat_category_mapping": {
                "VIP": item.pk,
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan == seatingplan
    with scopes_disabled():
        assert event.seats.count() == 3
        m = event.seat_category_mappings.get()
        assert event.seats.filter(product=None).count() == 3
    assert m.layout_category == 'VIP'
    assert m.product == item


@pytest.mark.django_db
def test_remove_seating(token_client, organizer, event, item, seatingplan):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan == seatingplan
    with scopes_disabled():
        assert event.seats.count() == 3
        assert event.seat_category_mappings.count() == 1

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": None
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan is None
    with scopes_disabled():
        assert event.seats.count() == 0
        assert event.seat_category_mappings.count() == 0


@pytest.mark.django_db
def test_remove_seating_forbidden(token_client, organizer, event, item, seatingplan, order_position):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan == seatingplan
    with scopes_disabled():
        assert event.seats.count() == 3
        assert event.seat_category_mappings.count() == 1

        order_position.seat = event.seats.first()
        order_position.save()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"seating_plan":["You can not change the plan since seat \\"0-0\\" is not ' \
                                    'present in the new plan and is already sold."]}'


@pytest.mark.django_db
def test_remove_seating_canceled_seat(token_client, organizer, event, item, seatingplan, order_position):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan == seatingplan
    with scopes_disabled():
        assert event.seats.count() == 3
        assert event.seat_category_mappings.count() == 1

        order_position.seat = event.seats.first()
        order_position.canceled = True
        order_position.save()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": None
        },
        format='json'
    )
    assert resp.status_code == 200
    order_position.refresh_from_db()
    assert order_position.seat is None


@pytest.mark.django_db
def test_no_seating_for_series(token_client, organizer, event, item, seatingplan, order_position):
    event.has_subevents = True
    event.save()
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Event series should not directly be assigned a seating plan."]}'


@pytest.mark.django_db
def test_event_create_with_seating(token_client, organizer, event, meta_prop, seatingplan):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2030",
            "seating_plan": seatingplan.pk,
            "meta_data": {
                meta_prop.name: "Conference"
            }
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        event = Event.objects.get(slug=resp.data['slug'])
        assert event.seating_plan == seatingplan
        assert event.seats.count() == 3
        assert event.seat_category_mappings.count() == 0


@pytest.mark.django_db
def test_event_create_with_seating_maps(token_client, organizer, event, meta_prop, seatingplan):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2030",
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Foo": 1,
            },
            "meta_data": {
                meta_prop.name: "Conference"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"seat_category_mapping":["You cannot specify seat category mappings on event creation."]}'


@pytest.mark.django_db
def test_get_event_settings(token_client, organizer, event):
    event.settings.imprint_url = "https://example.org"
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
    )
    assert resp.status_code == 200
    assert resp.data['imprint_url'] == "https://example.org"

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/settings/?explain=true'.format(organizer.slug, event.slug),
    )
    assert resp.status_code == 200
    assert resp.data['imprint_url'] == {
        "value": "https://example.org",
        "label": "Imprint URL",
        "help_text": "This should point e.g. to a part of your website that has your contact details and legal "
                     "information.",
        "readonly": False,
    }


@pytest.mark.django_db
def test_patch_event_settings(token_client, organizer, event):
    with mocker_context() as mocker:
        mocked = mocker.patch('pretix.presale.style.regenerate_css.apply_async')
        organizer.settings.imprint_url = 'https://example.org'
        resp = token_client.patch(
            '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
            {
                'imprint_url': 'https://example.com',
                'confirm_texts': [
                    {
                        'de': 'Ich bin mit den AGB einverstanden.'
                    }
                ],
                'reusable_media_active': True,  # readonly, ignored
            },
            format='json'
        )
        assert resp.status_code == 200
        assert resp.data['imprint_url'] == "https://example.com"
        assert not resp.data['reusable_media_active']
        event.settings.flush()
        assert event.settings.imprint_url == 'https://example.com'
        assert not event.settings.reusable_media_active
        mocked.assert_not_called()

        resp = token_client.patch(
            '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
            {
                'primary_color': '#ff0000',
                'theme_color_background': '#ff0000',
            },
            format='json'
        )
        assert resp.status_code == 200
        event.settings.flush()
        mocked.assert_any_call(args=(event.pk,))
        assert event.settings.primary_color == '#ff0000'

        resp = token_client.patch(
            '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
            {
                'primary_color': None,
                'theme_color_background': None,
            },
            format='json'
        )
        assert resp.status_code == 200
        event.settings.flush()
        assert event.settings.primary_color != '#ff0000'
        assert 'primary_color' not in event.settings._cache()

        resp = token_client.patch(
            '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
            {
                'imprint_url': None,
            },
            format='json'
        )
        assert resp.status_code == 200
        assert resp.data['imprint_url'] == "https://example.org"
        event.settings.flush()
        assert event.settings.imprint_url == 'https://example.org'

        resp = token_client.put(
            '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
            {
                'imprint_url': 'invalid'
            },
            format='json'
        )
        assert resp.status_code == 405

        locales = event.settings.locales

        resp = token_client.patch(
            '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
            {
                'locales': event.settings.locales + ['de', 'de-informal'],
            },
            format='json'
        )
        assert resp.status_code == 200
        assert set(resp.data['locales']) == set(locales + ['de', 'de-informal'])
        event.settings.flush()
        assert set(event.settings.locales) == set(locales + ['de', 'de-informal'])

        resp = token_client.patch(
            '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
            {
                'locales': locales,
            },
            format='json'
        )
        assert resp.status_code == 200
        assert set(resp.data['locales']) == set(locales)
        event.settings.flush()
        assert set(event.settings.locales) == set(locales)


@pytest.mark.django_db
def test_patch_event_settings_validation(token_client, organizer, event):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
        {
            'imprint_url': 'invalid'
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {
        'imprint_url': ['Enter a valid URL.']
    }

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
        {
            'invoice_address_required': True,
            'invoice_address_asked': False,
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {
        'invoice_address_required': ['You have to ask for invoice addresses if you want to make them required.']
    }

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
        {
            'cancel_allow_user_until': 'RELDATE/3/12:00/foobar/',
            'invoice_address_asked': False,
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {
        'cancel_allow_user_until': ['Invalid relative date']
    }


@pytest.mark.django_db
def test_patch_event_settings_file(token_client, organizer, event):
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

    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'application/pdf',
            'file': ContentFile('invalid pdf content')
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.pdf"',
    )
    assert r.status_code == 201
    file_id_pdf = r.data['id']

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
        {
            'logo_image': 'invalid'
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {
        'logo_image': ['The submitted file ID was not found.']
    }

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
        {
            'logo_image': file_id_pdf
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {
        'logo_image': ['The submitted file has a file type that is not allowed in this field.']
    }

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
        {
            'logo_image': file_id_png
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data['logo_image'].startswith('http')
    assert '/pub/' in resp.data['logo_image']

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/settings/'.format(organizer.slug, event.slug),
        {
            'logo_image': None
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data['logo_image'] is None
