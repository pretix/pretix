#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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

import pytest
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from pretix.base.models import Event, Organizer, Team


@pytest.fixture
@scopes_disabled()
def organizer():
    return Organizer.objects.create(name="Dummy", slug="dummy", plugins='pretix.plugins.banktransfer')


@pytest.fixture
@scopes_disabled()
def event(organizer):
    e = Event.objects.create(
        organizer=organizer,
        name="Dummy",
        slug="dummy",
        date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=timezone.utc),
        plugins="pretix.plugins.banktransfer,pretix.plugins.ticketoutputpdf,pretix.plugins.autocheckin",
        is_public=True,
    )
    e.settings.timezone = "Europe/Berlin"
    return e


@pytest.fixture
@scopes_disabled()
def item(event):
    return event.items.create(name="foo", default_price=3)


@pytest.fixture
@scopes_disabled()
def checkin_list(event):
    return event.checkin_lists.create(name="foo")


@pytest.fixture
@scopes_disabled()
def team(organizer):
    return Team.objects.create(
        organizer=organizer,
        name="Test-Team",
        all_events=True,
        can_change_teams=True,
        can_manage_gift_cards=True,
        can_change_items=True,
        can_create_events=True,
        can_change_event_settings=True,
        can_change_vouchers=True,
        can_view_vouchers=True,
        can_view_orders=True,
        can_change_orders=True,
        can_manage_customers=True,
        can_manage_reusable_media=True,
        can_change_organizer_settings=True,
    )


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
@scopes_disabled()
def token_client(client, team):
    t = team.tokens.create(name="Foo")
    client.credentials(HTTP_AUTHORIZATION="Token " + t.token)
    return client
