import datetime

import pytest

from pretix.base.models import Event, Organizer, Team, User


@pytest.fixture
def env(client):
    orga = Organizer.objects.create(name='CCC', slug='ccc')
    event = Event.objects.create(
        organizer=orga, name='30C3', slug='30c3',
        date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        plugins='pretix.plugins.stripe',
        live=True
    )
    event.settings.set('attendee_names_asked', False)
    event.settings.set('payment_stripe__enabled', True)
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    t = Team.objects.create(organizer=event.organizer, can_change_event_settings=True)
    t.members.add(user)
    t.limit_events.add(event)
    client.force_login(user)
    url = '/control/event/%s/%s/settings/payment' % (event.organizer.slug, event.slug)
    return client, event, url


@pytest.mark.django_db
def test_settings(env):
    client, event, url = env
    response = client.get(url, follow=True)
    assert response.status_code == 200
    assert 'stripe__enabled' in response.rendered_content
