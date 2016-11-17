import datetime

import pytest

from pretix.base.models import Event, EventPermission, Organizer, User


@pytest.fixture
def env(client):
    orga = Organizer.objects.create(name='CCC', slug='ccc')
    event = Event.objects.create(
        organizer=orga, name='30C3', slug='30c3',
        date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        plugins='pretix.plugins.paypal',
        live=True
    )
    event.settings.set('attendee_names_asked', False)
    event.settings.set('payment_paypal__enabled', True)
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    EventPermission.objects.create(user=user, event=event, can_change_settings=True)
    client.force_login(user)
    return client, event


@pytest.mark.django_db
def test_settings(env):
    client, event = env
    response = client.get('/control/event/%s/%s/settings/payment' % (event.organizer.slug, event.slug), follow=True)
    assert response.status_code == 200
    assert 'paypal__enabled' in response.rendered_content
