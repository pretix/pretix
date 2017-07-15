from datetime import datetime, time

import pytest
import pytz

from pretix.base.models import Event, Organizer
from pretix.base.reldate import RelativeDate, RelativeDateWrapper

TOKYO = pytz.timezone('Asia/Tokyo')


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
    rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=None, base_date_name='date_from'))
    assert rdw.datetime(event).astimezone(TOKYO) == datetime(2017, 12, 26, 5, 0, 0, tzinfo=TOKYO)
    assert rdw.to_string() == 'RELDATE/1/-/date_from/'


@pytest.mark.django_db
def test_relative_date_other_base_point(event):
    rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=None, base_date_name='presale_start'))
    assert rdw.datetime(event) == datetime(2017, 11, 30, 5, 0, 0, tzinfo=TOKYO)
    assert rdw.to_string() == 'RELDATE/1/-/presale_start/'

    # presale_end is unset, defaults to date_from
    rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=None, base_date_name='presale_end'))
    assert rdw.datetime(event) == datetime(2017, 12, 26, 5, 0, 0, tzinfo=TOKYO)
    assert rdw.to_string() == 'RELDATE/1/-/presale_end/'

    # subevent base
    se = event.subevents.create(name="SE1", date_from=datetime(2017, 11, 27, 5, 0, 0, tzinfo=TOKYO))
    rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=None, base_date_name='date_from'))
    assert rdw.datetime(se) == datetime(2017, 11, 26, 5, 0, 0, tzinfo=TOKYO)

    # presale_start is unset on subevent, default to event
    rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=None, base_date_name='presale_start'))
    assert rdw.datetime(se) == datetime(2017, 11, 30, 5, 0, 0, tzinfo=TOKYO)

    # presale_end is unset on all, default to date_from of subevent
    rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=None, base_date_name='presale_end'))
    assert rdw.datetime(se) == datetime(2017, 11, 26, 5, 0, 0, tzinfo=TOKYO)


@pytest.mark.django_db
def test_relative_date_with_time(event):
    rdw = RelativeDateWrapper(RelativeDate(days_before=1, time=time(8, 5, 13), base_date_name='date_from'))
    assert rdw.to_string() == 'RELDATE/1/08:05:13/date_from/'
    assert rdw.datetime(event) == datetime(2017, 12, 26, 8, 5, 13, tzinfo=TOKYO)


def test_unserialize():
    d = datetime(2017, 12, 25, 10, 0, 0, tzinfo=TOKYO)
    rdw = RelativeDateWrapper.from_string(d.isoformat())
    assert rdw.data == d

    rdw = RelativeDateWrapper.from_string('RELDATE/1/-/date_from/')
    assert rdw.data == RelativeDate(days_before=1, time=None, base_date_name='date_from')

    rdw = RelativeDateWrapper.from_string('RELDATE/1/18:05:13/date_from/')
    assert rdw.data == RelativeDate(days_before=1, time=time(18, 5, 13), base_date_name='date_from')
