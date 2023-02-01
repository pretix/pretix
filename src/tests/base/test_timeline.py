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
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django_scopes import scope

from pretix.base.i18n import language
from pretix.base.models import Event, Organizer
from pretix.base.timeline import timeline_for_event

tz = ZoneInfo('Europe/Berlin')


def one(iterable):
    found = False
    for it in iterable:
        if it:
            if found:
                return False
            else:
                found = True
    return found


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=datetime(2017, 10, 22, 12, 0, 0, tzinfo=tz),
        date_to=datetime(2017, 10, 23, 23, 0, 0, tzinfo=tz),
    )
    with scope(organizer=o):
        yield event


@pytest.fixture
def item(event):
    return event.items.create(name='Ticket', default_price=Decimal('23.00'))


@pytest.mark.django_db
def test_event_dates(event):
    with language('en'):
        tl = timeline_for_event(event)
        assert one([
            e for e in tl
            if e.event == event and e.datetime == event.date_from and e.description == 'Your event starts'
        ])
        assert one([
            e for e in tl
            if e.event == event and e.datetime == event.date_to and e.description == 'Your event ends'
        ])
