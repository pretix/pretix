from datetime import timedelta

import pytest
from django.utils.timezone import now

from pretix.base.models import Event, Organizer


@pytest.fixture
def env():
    o = Organizer.objects.create(name='MRMCD e.V.', slug='mrmcd')
    event = Event.objects.create(
        organizer=o, name='MRMCD2015', slug='2015',
        date_from=now() + timedelta(days=10)
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
