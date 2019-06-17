from datetime import datetime
from decimal import Decimal

import pytest
import pytz
from django_scopes import scope

from pretix.base.models import Event, Organizer
from pretix.base.timeline import timeline_for_event

tz = pytz.timezone('Europe/Berlin')


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
    tl = timeline_for_event(event)
    assert one([
        e for e in tl
        if e.event == event and e.datetime == event.date_from and e.description == 'Your event starts'
    ])
    assert one([
        e for e in tl
        if e.event == event and e.datetime == event.date_to and e.description == 'Your event ends'
    ])
