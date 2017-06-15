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
        date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC), plugins='pretix.plugins.banktransfer'
    )


@pytest.fixture
def team(organizer):
    return Team.objects.create(organizer=organizer)


@pytest.fixture
def user():
    return User.objects.create_user('dummy@dummy.dummy', 'dummy')
