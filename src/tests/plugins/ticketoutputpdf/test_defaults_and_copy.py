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

import pytest
from django.test import override_settings
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Event, Item, Organizer, Team, User


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.ticketoutputpdf'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    t = Team.objects.create(organizer=event.organizer, can_create_events=True, can_change_event_settings=True, can_change_items=True)
    t.members.add(user)
    t.limit_events.add(event)
    item1 = Item.objects.create(event=event, name="Ticket", default_price=23)
    tl = event.ticket_layouts.create(name="Foo", default=True, layout='[]')
    return event, user, tl, item1


@pytest.mark.django_db
@override_settings(PRETIX_PLUGINS_DEFAULT="pretix.plugins.ticketoutputpdf")
def test_api_clone_query(env, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post('/api/v1/organizers/{}/events/?clone_from={}'.format(env[0].organizer.slug, env[0].slug), data={
        "name": {"en": "Cloned"},
        "slug": "cloned",
        "live": False,
        "testmode": False,
        "currency": "EUR",
        "date_from": "2017-12-27T10:00:00Z",
        "plugins": ["pretix.plugins.ticketoutputpdf"],
    }, content_type='application/json')
    assert r.status_code == 201
    with scopes_disabled():
        e = Event.objects.get(slug="cloned")
        assert e.ticket_layouts.count() == 1
        assert e.ticket_layouts.get().name == "Foo"


@pytest.mark.django_db
@override_settings(PRETIX_PLUGINS_DEFAULT="pretix.plugins.ticketoutputpdf")
def test_api_clone_path(env, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post('/api/v1/organizers/{}/events/{}/clone/'.format(env[0].organizer.slug, env[0].slug), data={
        "name": {"en": "Cloned"},
        "slug": "cloned",
        "live": False,
        "testmode": False,
        "currency": "EUR",
        "date_from": "2017-12-27T10:00:00Z",
        "plugins": ["pretix.plugins.ticketoutputpdf"],
    }, content_type='application/json')
    assert r.status_code == 201
    with scopes_disabled():
        e = Event.objects.get(slug="cloned")
        assert e.ticket_layouts.count() == 1
        assert e.ticket_layouts.get().name == "Foo"


@pytest.mark.django_db
@override_settings(PRETIX_PLUGINS_DEFAULT="pretix.plugins.ticketoutputpdf")
def test_api_create(env, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post('/api/v1/organizers/{}/events/'.format(env[0].organizer.slug), data={
        "name": {"en": "Cloned"},
        "slug": "cloned",
        "live": False,
        "testmode": False,
        "currency": "EUR",
        "date_from": "2017-12-27T10:00:00Z",
        "plugins": ["pretix.plugins.ticketoutputpdf"],
    }, content_type='application/json')
    assert r.status_code == 201
    with scopes_disabled():
        e = Event.objects.get(slug="cloned")
        assert e.ticket_layouts.count() == 1
        assert e.ticket_layouts.get().name == "Default layout"


@pytest.mark.django_db
@override_settings(PRETIX_PLUGINS_DEFAULT="pretix.plugins.ticketoutputpdf")
def test_control_clone(env, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post(f'/control/events/add?clone={env[0].pk}', {
        'event_wizard-current_step': 'foundation',
        'event_wizard-prefix': 'event_wizard',
        'foundation-organizer': env[0].organizer.pk,
        'foundation-locales': ('en', 'de')
    })
    client.post(f'/control/events/add?clone={env[0].pk}', {
        'event_wizard-current_step': 'basics',
        'event_wizard-prefix': 'event_wizard',
        'basics-name_0': '33C3',
        'basics-name_1': '33C3',
        'basics-slug': 'cloned',
        'basics-date_from_0': '2016-12-27',
        'basics-date_from_1': '10:00:00',
        'basics-date_to_0': '2016-12-30',
        'basics-date_to_1': '19:00:00',
        'basics-location_0': 'Hamburg',
        'basics-location_1': 'Hamburg',
        'basics-currency': 'EUR',
        'basics-tax_rate': '19.00',
        'basics-locale': 'en',
        'basics-timezone': 'Europe/Berlin',
        'basics-presale_start_0': '2016-11-01',
        'basics-presale_start_1': '10:00:00',
        'basics-presale_end_0': '2016-11-30',
        'basics-presale_end_1': '18:00:00',
    })
    with scopes_disabled():
        e = Event.objects.get(slug="cloned")
        assert e.ticket_layouts.count() == 1
        assert e.ticket_layouts.get().name == "Foo"


@pytest.mark.django_db
@override_settings(PRETIX_PLUGINS_DEFAULT="pretix.plugins.ticketoutputpdf")
def test_control_create(env, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/events/add', {
        'event_wizard-current_step': 'foundation',
        'event_wizard-prefix': 'event_wizard',
        'foundation-organizer': env[0].organizer.pk,
        'foundation-locales': ('en', 'de')
    })
    client.post('/control/events/add', {
        'event_wizard-current_step': 'basics',
        'event_wizard-prefix': 'event_wizard',
        'basics-name_0': '33C3',
        'basics-name_1': '33C3',
        'basics-slug': 'cloned',
        'basics-date_from_0': '2016-12-27',
        'basics-date_from_1': '10:00:00',
        'basics-date_to_0': '2016-12-30',
        'basics-date_to_1': '19:00:00',
        'basics-location_0': 'Hamburg',
        'basics-location_1': 'Hamburg',
        'basics-currency': 'EUR',
        'basics-tax_rate': '19.00',
        'basics-locale': 'en',
        'basics-timezone': 'Europe/Berlin',
        'basics-presale_start_0': '2016-11-01',
        'basics-presale_start_1': '10:00:00',
        'basics-presale_end_0': '2016-11-30',
        'basics-presale_end_1': '18:00:00',
    })
    client.post('/control/events/add', {
        'event_wizard-current_step': 'copy',
        'event_wizard-prefix': 'event_wizard',
        'copy-copy_from_event': ''
    })
    with scopes_disabled():
        e = Event.objects.get(slug="cloned")
        assert e.ticket_layouts.count() == 1
        assert e.ticket_layouts.get().name == "Default layout"
