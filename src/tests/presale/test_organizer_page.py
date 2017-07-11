from datetime import datetime, timedelta

import pytest
from django.utils.timezone import now
from pytz import UTC

from pretix.base.models import Event, Organizer


@pytest.fixture
def env():
    o = Organizer.objects.create(name='MRMCD e.V.', slug='mrmcd')
    event = Event.objects.create(
        organizer=o, name='MRMCD2015', slug='2015',
        date_from=now() + timedelta(days=10),
        live=True
    )
    return o, event


@pytest.mark.django_db
def test_organizer_page_shown(env, client):
    r = client.get('/mrmcd/')
    assert r.status_code == 200
    assert 'MRMCD e.V.' in r.rendered_content


@pytest.mark.django_db
def test_public_event_on_page(env, client):
    env[1].is_public = True
    env[1].save()
    r = client.get('/mrmcd/')
    assert 'MRMCD2015' in r.rendered_content


@pytest.mark.django_db
def test_non_public_event_not_on_page(env, client):
    env[1].is_public = False
    env[1].save()
    r = client.get('/mrmcd/')
    assert 'MRMCD2015' not in r.rendered_content


@pytest.mark.django_db
def test_running_event_on_current_page(env, client):
    env[1].date_from = now() - timedelta(days=2)
    env[1].date_to = now() + timedelta(days=2)
    env[1].is_public = True
    env[1].save()
    r = client.get('/mrmcd/')
    assert 'MRMCD2015' in r.rendered_content


@pytest.mark.django_db
def test_past_event_shown_on_archive_page(env, client):
    env[1].date_from = now() - timedelta(days=2)
    env[1].date_to = now() - timedelta(days=2)
    env[1].is_public = True
    env[1].save()
    r = client.get('/mrmcd/?old=1')
    assert 'MRMCD2015' in r.rendered_content


@pytest.mark.django_db
def test_event_not_shown_on_archive_page(env, client):
    env[1].is_public = True
    env[1].save()
    r = client.get('/mrmcd/?old=1')
    assert 'MRMCD2015' not in r.rendered_content


@pytest.mark.django_db
def test_past_event_not_shown(env, client):
    env[1].date_from = now() - timedelta(days=2)
    env[1].date_to = now() - timedelta(days=2)
    env[1].is_public = True
    env[1].save()
    r = client.get('/mrmcd/')
    assert 'MRMCD2015' not in r.rendered_content


@pytest.mark.django_db
def test_empty_message(env, client):
    env[1].is_public = False
    env[1].save()
    r = client.get('/mrmcd/')
    assert 'No public upcoming events found' in r.rendered_content


@pytest.mark.django_db
def test_different_organizer_not_shown(env, client):
    o = Organizer.objects.create(name='CCC e.V.', slug='ccc')
    Event.objects.create(
        organizer=o, name='32C3', slug='32c3',
        date_from=now() + timedelta(days=10), is_public=True
    )
    r = client.get('/mrmcd/')
    assert '32C3' not in r.rendered_content


@pytest.mark.django_db
def test_calendar(env, client):
    env[0].settings.event_list_type = 'calendar'
    e = Event.objects.create(
        organizer=env[0], name='MRMCD2017', slug='2017',
        date_from=datetime(now().year + 1, 9, 1, tzinfo=UTC),
        live=True
    )
    r = client.get('/mrmcd/')
    assert 'MRMCD2017' not in r.rendered_content
    e.is_public = True
    e.save()
    r = client.get('/mrmcd/')
    assert 'MRMCD2017' in r.rendered_content
    assert 'September %d' % (now().year + 1) in r.rendered_content
    r = client.get('/mrmcd/events/2017/10/')
    assert 'MRMCD2017' not in r.rendered_content
    assert 'October 2017' in r.rendered_content
    r = client.get('/mrmcd/events/?month=10&year=2017')
    assert 'MRMCD2017' not in r.rendered_content
    assert 'October 2017' in r.rendered_content
