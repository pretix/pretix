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
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest
from django_scopes import scope

from pretix.base.models import Event, Organizer
from pretix.base.reldate import RelativeDate, RelativeDateWrapper

TOKYO = ZoneInfo('Asia/Tokyo')
BERLIN = ZoneInfo('Europe/Berlin')


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=datetime(2017, 12, 27, 5, 0, 0, tzinfo=TOKYO),
        presale_start=datetime(2017, 12, 1, 5, 0, 0, tzinfo=TOKYO),
        plugins='pretix.plugins.banktransfer'

    )
    event.settings.timezone = "Asia/Tokyo"
    return event


@pytest.mark.django_db
def test_absolute_date(event):
    d = datetime(2017, 12, 25, 5, 0, 0, tzinfo=TOKYO)
    rdw = RelativeDateWrapper(d)
    assert rdw.datetime(event) == d
    assert rdw.to_string() == d.isoformat()


@pytest.mark.django_db
def test_relative_date_without_time(event):
    rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=None, base_date_name='date_from', minutes_before=None))
    assert rdw.datetime(event).astimezone(TOKYO) == datetime(2017, 12, 26, 5, 0, 0, tzinfo=TOKYO)
    assert rdw.to_string() == 'RELDATE/1/-/date_from/'


@pytest.mark.django_db
def test_relative_date_other_base_point(event):
    with scope(organizer=event.organizer):
        rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=None, base_date_name='presale_start', minutes_before=None))
        assert rdw.datetime(event) == datetime(2017, 11, 30, 5, 0, 0, tzinfo=TOKYO)
        assert rdw.to_string() == 'RELDATE/1/-/presale_start/'

        # presale_end is unset, defaults to date_from
        rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=None, base_date_name='presale_end', minutes_before=None))
        assert rdw.datetime(event) == datetime(2017, 12, 26, 5, 0, 0, tzinfo=TOKYO)
        assert rdw.to_string() == 'RELDATE/1/-/presale_end/'

        # subevent base
        se = event.subevents.create(name="SE1", date_from=datetime(2017, 11, 27, 5, 0, 0, tzinfo=TOKYO))
        rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=None, base_date_name='date_from', minutes_before=None))
        assert rdw.datetime(se) == datetime(2017, 11, 26, 5, 0, 0, tzinfo=TOKYO)

        # presale_start is unset on subevent, default to event
        rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=None, base_date_name='presale_start', minutes_before=None))
        assert rdw.datetime(se) == datetime(2017, 11, 30, 5, 0, 0, tzinfo=TOKYO)

        # presale_end is unset on all, default to date_from of subevent
        rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=None, base_date_name='presale_end', minutes_before=None))
        assert rdw.datetime(se) == datetime(2017, 11, 26, 5, 0, 0, tzinfo=TOKYO)


@pytest.mark.django_db
def test_relative_date_in_minutes(event):
    rdw = RelativeDateWrapper(RelativeDate(days_before=0, time=None, base_date_name='date_from', minutes_before=60))
    assert rdw.to_string() == 'RELDATE/minutes/60/date_from/'
    assert rdw.datetime(event) == datetime(2017, 12, 27, 4, 0, 0, tzinfo=TOKYO)


@pytest.mark.django_db
def test_relative_date_with_time(event):
    rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=time(8, 5, 13), base_date_name='date_from', minutes_before=None))
    assert rdw.to_string() == 'RELDATE/1/08:05:13/date_from/'
    assert rdw.datetime(event) == datetime(2017, 12, 26, 8, 5, 13, tzinfo=TOKYO)


@pytest.mark.django_db
def test_relative_date_with_time_around_dst(event):
    event.settings.timezone = "Europe/Berlin"
    event.date_from = datetime(2020, 3, 29, 18, 0, 0, tzinfo=BERLIN)

    rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=time(18, 0, 0), base_date_name='date_from', minutes_before=None))
    assert rdw.to_string() == 'RELDATE/1/18:00:00/date_from/'
    assert rdw.datetime(event) == datetime(2020, 3, 28, 18, 0, 0, tzinfo=BERLIN)

    rdw = RelativeDateWrapper(RelativeDate(days_before=0, time=time(2, 30, 0), base_date_name='date_from', minutes_before=None))
    assert rdw.to_string() == 'RELDATE/0/02:30:00/date_from/'
    assert rdw.datetime(event) == datetime(2020, 3, 29, 2, 30, 0, tzinfo=BERLIN)

    event.date_from = datetime(2020, 10, 25, 18, 0, 0, tzinfo=BERLIN)

    rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=time(18, 0, 0), base_date_name='date_from', minutes_before=None))
    assert rdw.to_string() == 'RELDATE/1/18:00:00/date_from/'
    assert rdw.datetime(event) == datetime(2020, 10, 24, 18, 0, 0, tzinfo=BERLIN)

    rdw = RelativeDateWrapper(RelativeDate(days_before=0, time=time(2, 30, 0), base_date_name='date_from', minutes_before=None))
    assert rdw.to_string() == 'RELDATE/0/02:30:00/date_from/'
    assert rdw.datetime(event) == datetime(2020, 10, 25, 2, 30, 0, tzinfo=BERLIN)


def test_unserialize():
    d = datetime(2017, 12, 25, 10, 0, 0, tzinfo=TOKYO)
    rdw = RelativeDateWrapper.from_string(d.isoformat())
    assert rdw.data == d

    rdw = RelativeDateWrapper.from_string('RELDATE/1/-/date_from/')
    assert rdw.data == RelativeDate(days_before=1, time=None, base_date_name='date_from', minutes_before=None)

    rdw = RelativeDateWrapper.from_string('RELDATE/1/18:05:13/date_from/')
    assert rdw.data == RelativeDate(days_before=1, time=time(18, 5, 13), base_date_name='date_from', minutes_before=None)

    rdw = RelativeDateWrapper.from_string('RELDATE/minutes/60/date_from/')
    assert rdw.data == RelativeDate(days_before=0, time=None, base_date_name='date_from', minutes_before=60)
