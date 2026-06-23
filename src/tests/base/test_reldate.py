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
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django_scopes import scope, scopes_disabled

from pretix.base.models import Event, Order, OrderPosition, Organizer
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
    rdw = RelativeDateWrapper(RelativeDate(days=1, time=None, base_date_name='event__date_from', minutes=None))
    assert rdw.datetime(event).astimezone(TOKYO) == datetime(2017, 12, 26, 5, 0, 0, tzinfo=TOKYO)
    assert rdw.to_string() == 'RELDATE/1/-/event__date_from/'
    rdw = RelativeDateWrapper(RelativeDate(days=1, time=None, base_date_name='event__date_from', minutes=None, is_after=True))
    assert rdw.datetime(event).astimezone(TOKYO) == datetime(2017, 12, 28, 5, 0, 0, tzinfo=TOKYO)
    assert rdw.to_string() == 'RELDATE/1/-/event__date_from/after'


@pytest.mark.django_db
def test_relative_date_other_base_point(event):
    with scope(organizer=event.organizer):
        rdw = RelativeDateWrapper(RelativeDate(days=1, time=None, base_date_name='event__presale_start', minutes=None))
        assert rdw.datetime(event) == datetime(2017, 11, 30, 5, 0, 0, tzinfo=TOKYO)
        assert rdw.to_string() == 'RELDATE/1/-/event__presale_start/'

        # presale_end is unset, defaults to date_from
        rdw = RelativeDateWrapper(RelativeDate(days=1, time=None, base_date_name='event__presale_end', minutes=None))
        assert rdw.datetime(event) == datetime(2017, 12, 26, 5, 0, 0, tzinfo=TOKYO)
        assert rdw.to_string() == 'RELDATE/1/-/event__presale_end/'

        # subevent base
        se = event.subevents.create(name="SE1", date_from=datetime(2017, 11, 27, 5, 0, 0, tzinfo=TOKYO))
        rdw = RelativeDateWrapper(RelativeDate(days=1, time=None, base_date_name='event__date_from', minutes=None))
        assert rdw.datetime(se) == datetime(2017, 11, 26, 5, 0, 0, tzinfo=TOKYO)

        # presale_start is unset on subevent, default to event
        rdw = RelativeDateWrapper(RelativeDate(days=1, time=None, base_date_name='event__presale_start', minutes=None))
        assert rdw.datetime(se) == datetime(2017, 11, 30, 5, 0, 0, tzinfo=TOKYO)

        # presale_end is unset on all, default to date_from of subevent
        rdw = RelativeDateWrapper(RelativeDate(days=1, time=None, base_date_name='event__presale_end', minutes=None))
        assert rdw.datetime(se) == datetime(2017, 11, 26, 5, 0, 0, tzinfo=TOKYO)


@pytest.mark.django_db
def test_relative_date_in_minutes(event):
    rdw = RelativeDateWrapper(RelativeDate(days=0, time=None, base_date_name='event__date_from', minutes=60))
    assert rdw.to_string() == 'RELDATE/minutes/60/event__date_from/'
    assert rdw.datetime(event) == datetime(2017, 12, 27, 4, 0, 0, tzinfo=TOKYO)
    rdw = RelativeDateWrapper(RelativeDate(days=0, time=None, base_date_name='event__date_from', minutes=60, is_after=True))
    assert rdw.to_string() == 'RELDATE/minutes/60/event__date_from/after'
    assert rdw.datetime(event) == datetime(2017, 12, 27, 6, 0, 0, tzinfo=TOKYO)


@pytest.mark.django_db
def test_relative_date_with_time(event):
    rdw = RelativeDateWrapper(RelativeDate(days=1, time=time(8, 5, 13), base_date_name='event__date_from', minutes=None))
    assert rdw.to_string() == 'RELDATE/1/08:05:13/event__date_from/'
    assert rdw.datetime(event) == datetime(2017, 12, 26, 8, 5, 13, tzinfo=TOKYO)
    rdw = RelativeDateWrapper(RelativeDate(days=1, time=time(8, 5, 13), base_date_name='event__date_from', minutes=None, is_after=True))
    assert rdw.to_string() == 'RELDATE/1/08:05:13/event__date_from/after'
    assert rdw.datetime(event) == datetime(2017, 12, 28, 8, 5, 13, tzinfo=TOKYO)


@pytest.mark.django_db
def test_relative_date_with_time_around_dst(event):
    event.settings.timezone = "Europe/Berlin"
    event.date_from = datetime(2020, 3, 29, 18, 0, 0, tzinfo=BERLIN)

    rdw = RelativeDateWrapper(RelativeDate(days=1, time=time(18, 0, 0), base_date_name='event__date_from', minutes=None))
    assert rdw.to_string() == 'RELDATE/1/18:00:00/event__date_from/'
    assert rdw.datetime(event) == datetime(2020, 3, 28, 18, 0, 0, tzinfo=BERLIN)

    rdw = RelativeDateWrapper(RelativeDate(days=0, time=time(2, 30, 0), base_date_name='event__date_from', minutes=None))
    assert rdw.to_string() == 'RELDATE/0/02:30:00/event__date_from/'
    assert rdw.datetime(event) == datetime(2020, 3, 29, 2, 30, 0, tzinfo=BERLIN)

    event.date_from = datetime(2020, 10, 25, 18, 0, 0, tzinfo=BERLIN)

    rdw = RelativeDateWrapper(RelativeDate(days=1, time=time(18, 0, 0), base_date_name='event__date_from', minutes=None))
    assert rdw.to_string() == 'RELDATE/1/18:00:00/event__date_from/'
    assert rdw.datetime(event) == datetime(2020, 10, 24, 18, 0, 0, tzinfo=BERLIN)

    rdw = RelativeDateWrapper(RelativeDate(days=0, time=time(2, 30, 0), base_date_name='event__date_from', minutes=None))
    assert rdw.to_string() == 'RELDATE/0/02:30:00/event__date_from/'
    assert rdw.datetime(event) == datetime(2020, 10, 25, 2, 30, 0, tzinfo=BERLIN)


def test_unserialize_backwards_compatibility():
    d = datetime(2017, 12, 25, 10, 0, 0, tzinfo=TOKYO)
    rdw = RelativeDateWrapper.from_string(d.isoformat())
    assert rdw.data == d

    # keeping the test for the old from_string_format to ensure that we don't break anything
    rdw = RelativeDateWrapper.from_string('RELDATE/1/-/date_from/')
    assert rdw.data == RelativeDate(days=1, time=None, base_date_name='date_from', minutes=None)

    # keeping the test for the old from_string_format to ensure that we don't break anything
    rdw = RelativeDateWrapper.from_string('RELDATE/1/18:05:13/date_from/')
    assert rdw.data == RelativeDate(days=1, time=time(18, 5, 13), base_date_name='date_from', minutes=None)

    # keeping the test for the old from_string_format to ensure that we don't break anything
    rdw = RelativeDateWrapper.from_string('RELDATE/minutes/60/date_from/')
    assert rdw.data == RelativeDate(days=0, time=None, base_date_name='date_from', minutes=60)


def test_backwards_compatibility():
    # the data model of RelativeDate had to be extended to support other models as relation target
    # previously only:
    # - date_from
    # - date_to
    # - date_admission
    # - presale_start
    # - presale_end
    # where valid values for the fourth slot (base_date_names) of the serialized form.
    # the relationship in this case always pointed at event
    # so any preexisting base_date_names without __ should continue to work and upgrade to event__{old_base_date_name}
    d = datetime(2017, 12, 25, 10, 0, 0, tzinfo=TOKYO)
    rdw = RelativeDateWrapper.from_string(d.isoformat())
    assert rdw.data == d

    rdw = RelativeDateWrapper.from_string('RELDATE/1/-/date_from/')
    assert rdw.to_string() == 'RELDATE/1/-/event__date_from/'

    rdw = RelativeDateWrapper.from_string('RELDATE/1/-/date_to/')
    assert rdw.to_string() == 'RELDATE/1/-/event__date_to/'

    rdw = RelativeDateWrapper.from_string('RELDATE/1/-/date_admission/')
    assert rdw.to_string() == 'RELDATE/1/-/event__date_admission/'

    rdw = RelativeDateWrapper.from_string('RELDATE/1/-/presale_start/')
    assert rdw.to_string() == 'RELDATE/1/-/event__presale_start/'

    rdw = RelativeDateWrapper.from_string('RELDATE/1/-/presale_end/')
    assert rdw.to_string() == 'RELDATE/1/-/event__presale_end/'

    # new order base_date_names should not work without __
    with pytest.raises(TypeError):
        RelativeDateWrapper.from_string('RELDATE/1/-/datetime/')
    with pytest.raises(TypeError):
        RelativeDateWrapper.from_string('RELDATE/1/-/expires/')


@pytest.mark.django_db
def test_relative_to_order(event):
    with scope(organizer=event.organizer):
        order_moment = datetime(2020, 3, 29, 18, 0, 0, tzinfo=TOKYO)

        order = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, secret="k24fiuwvu8kxz3y1",
            datetime=order_moment,
            expires=order_moment + timedelta(days=10),
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
            total=23, locale='en'
        )

        rdw = RelativeDateWrapper(RelativeDate(days=1, time=None, base_date_name='order__datetime', minutes=None, is_after=True))
        assert rdw.datetime(order).astimezone(TOKYO) == datetime(2020, 3, 30, 18, 0, 0, tzinfo=TOKYO)
        assert rdw.to_string() == 'RELDATE/1/-/order__datetime/after'
