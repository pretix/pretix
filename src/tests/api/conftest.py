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
from datetime import datetime

import pytest
from django.test import utils
from django.utils.timezone import now
from django_scopes import scopes_disabled
from pytz import UTC
from rest_framework.test import APIClient

from pretix.base.models import Device, Event, Organizer, Team, User
from pretix.base.models.devices import generate_api_token


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
@scopes_disabled()
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
@scopes_disabled()
def meta_prop(organizer):
    return organizer.meta_properties.create(name="type", default="Concert")


@pytest.fixture
@scopes_disabled()
def event(organizer, meta_prop):
    e = Event.objects.create(
        organizer=organizer, name='Dummy', slug='dummy',
        date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC),
        plugins='pretix.plugins.banktransfer,pretix.plugins.ticketoutputpdf',
        is_public=True
    )
    e.meta_values.create(property=meta_prop, value="Conference")
    e.item_meta_properties.create(name="day", default="Monday")
    e.settings.timezone = 'Europe/Berlin'
    return e


@pytest.fixture
@scopes_disabled()
def event2(organizer, meta_prop):
    e = Event.objects.create(
        organizer=organizer, name='Dummy2', slug='dummy2',
        date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC),
        plugins='pretix.plugins.banktransfer,pretix.plugins.ticketoutputpdf'
    )
    e.meta_values.create(property=meta_prop, value="Conference")
    return e


@pytest.fixture
@scopes_disabled()
def event3(organizer, meta_prop):
    e = Event.objects.create(
        organizer=organizer, name='Dummy3', slug='dummy3',
        date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC),
        plugins='pretix.plugins.banktransfer,pretix.plugins.ticketoutputpdf'
    )
    e.meta_values.create(property=meta_prop, value="Conference")
    return e


@pytest.fixture
@scopes_disabled()
def team(organizer):
    return Team.objects.create(
        organizer=organizer,
        name="Test-Team",
        can_change_teams=True,
        can_manage_gift_cards=True,
        can_change_items=True,
        can_create_events=True,
        can_change_event_settings=True,
        can_change_vouchers=True,
        can_view_vouchers=True,
        can_change_orders=True,
        can_change_organizer_settings=True
    )


@pytest.fixture
@scopes_disabled()
def device(organizer):
    return Device.objects.create(
        organizer=organizer,
        all_events=True,
        name='Foo',
        initialized=now(),
        api_token=generate_api_token()
    )


@pytest.fixture
def user():
    return User.objects.create_user('dummy@dummy.dummy', 'dummy')


@pytest.fixture
@scopes_disabled()
def user_client(client, team, user):
    team.can_view_orders = True
    team.can_view_vouchers = True
    team.all_events = True
    team.save()
    team.members.add(user)
    client.force_authenticate(user=user)
    return client


@pytest.fixture
@scopes_disabled()
def token_client(client, team):
    team.can_view_orders = True
    team.can_view_vouchers = True
    team.all_events = True
    team.save()
    t = team.tokens.create(name='Foo')
    client.credentials(HTTP_AUTHORIZATION='Token ' + t.token)
    return client


@pytest.fixture
def device_client(client, device):
    client.credentials(HTTP_AUTHORIZATION='Device ' + device.api_token)
    return client


@pytest.fixture
@scopes_disabled()
def subevent(event, meta_prop):
    event.has_subevents = True
    event.save()
    se = event.subevents.create(name="Foobar", date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC))

    se.meta_values.create(property=meta_prop, value="Workshop")
    return se


@pytest.fixture
@scopes_disabled()
def subevent2(event2, meta_prop):
    event2.has_subevents = True
    event2.save()
    se = event2.subevents.create(name="Foobar", date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC))

    se.meta_values.create(property=meta_prop, value="Workshop")
    return se


@pytest.fixture
@scopes_disabled()
def taxrule(event):
    return event.tax_rules.create(name="VAT", rate=19)


@pytest.fixture
@scopes_disabled()
def taxrule0(event):
    return event.tax_rules.create(name="VAT", rate=0)


@pytest.fixture
@scopes_disabled()
def taxrule2(event2):
    return event2.tax_rules.create(name="VAT", rate=25)


utils.setup_databases = scopes_disabled()(utils.setup_databases)
