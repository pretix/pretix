from datetime import datetime

import pytest
from pytz import UTC
from rest_framework.test import APIClient

from pretix.base.models import Event, Organizer, Team, User


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
def event(organizer):
    return Event.objects.create(
        organizer=organizer, name='Dummy', slug='dummy',
        date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC),
        plugins='pretix.plugins.banktransfer,pretix.plugins.ticketoutputpdf'
    )


@pytest.fixture
def team(organizer):
    return Team.objects.create(organizer=organizer)


@pytest.fixture
def user():
    return User.objects.create_user('dummy@dummy.dummy', 'dummy')


@pytest.fixture
def token_client(client, team):
    team.can_view_orders = True
    team.can_view_vouchers = True
    team.all_events = True
    team.save()
    t = team.tokens.create(name='Foo')
    client.credentials(HTTP_AUTHORIZATION='Token ' + t.token)
    return client


@pytest.fixture
def subevent(event):
    event.has_subevents = True
    event.save()
    return event.subevents.create(name="Foobar",
                                  date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC))


@pytest.fixture
def taxrule(event):
    return event.tax_rules.create(name="VAT", rate=19)
