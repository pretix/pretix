from datetime import datetime, timedelta

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled
from pytz import UTC

from pretix.base.models import Event, Organizer


@pytest.fixture
def env():
    o = Organizer.objects.create(name='MRMCD e.V.', slug='mrmcd')
    event = Event.objects.create(
        organizer=o, name='MRMCD2015', slug='2015',
        date_from=now() + timedelta(days=10),
        live=True, is_public=False
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
def test_attributes_on_page(env, client):
    env[1].is_public = True
    env[1].save()

    prop = env[0].meta_properties.create(name='loc', default='HH')
    propval = env[1].meta_values.create(value='HD', property=prop)

    r = client.get('/mrmcd/?attr[loc]=HD')
    assert 'MRMCD2015' in r.rendered_content
    r = client.get('/mrmcd/?attr[loc]=MA')
    assert 'MRMCD2015' not in r.rendered_content
    r = client.get('/mrmcd/?attr[loc]=HH')
    assert 'MRMCD2015' not in r.rendered_content
    propval.delete()
    r = client.get('/mrmcd/?attr[loc]=HH')
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
        live=True, is_public=False
    )
    r = client.get('/mrmcd/?style=calendar')
    assert 'MRMCD2017' not in r.rendered_content
    e.is_public = True
    e.save()
    r = client.get('/mrmcd/?style=calendar')
    assert 'MRMCD2017' in r.rendered_content
    assert 'September %d' % (now().year + 1) in r.rendered_content
    r = client.get('/mrmcd/?style=calendar&month=10&year=2017')
    assert 'MRMCD2017' not in r.rendered_content
    assert 'October 2017' in r.rendered_content


@pytest.mark.django_db
def test_attributes_in_calendar(env, client):
    env[0].settings.event_list_type = 'calendar'
    e = Event.objects.create(
        organizer=env[0], name='MRMCD2017', slug='2017',
        date_from=datetime(now().year + 1, 9, 1, tzinfo=UTC),
        live=True, is_public=True
    )
    prop = env[0].meta_properties.create(name='loc')
    e.meta_values.create(value='HD', property=prop)

    r = client.get('/mrmcd/?attr[loc]=HD&style=calendar')
    assert 'MRMCD2017' in r.rendered_content
    r = client.get('/mrmcd/?attr[loc]=MA&style=calendar')
    assert 'MRMCD2017' not in r.rendered_content


@pytest.mark.django_db
def test_ics(env, client):
    e = Event.objects.create(
        organizer=env[0], name='MRMCD2017', slug='2017',
        date_from=datetime(now().year + 1, 9, 1, tzinfo=UTC),
        live=True, is_public=False
    )
    r = client.get('/mrmcd/events/ical/')
    assert b'MRMCD2017' not in r.content
    e.is_public = True
    e.save()
    r = client.get('/mrmcd/events/ical/')
    assert b'MRMCD2017' in r.content


@pytest.mark.django_db
def test_ics_subevents(env, client):
    e = Event.objects.create(
        organizer=env[0], name='MRMCD2017', slug='2017',
        date_from=datetime(now().year + 1, 9, 1, tzinfo=UTC),
        live=True, is_public=True, has_subevents=True
    )
    with scopes_disabled():
        e.subevents.create(date_from=now(), name='SE1', active=True)
    r = client.get('/mrmcd/events/ical/')
    assert b'MRMCD2017' not in r.content
    assert b'SE1' in r.content


@pytest.mark.django_db
def test_ics_subevents_attributes(env, client):
    e0 = Event.objects.create(
        organizer=env[0], name='DS2017', slug='DS2017',
        date_from=datetime(now().year + 1, 9, 1, tzinfo=UTC),
        live=True, is_public=True
    )
    e = Event.objects.create(
        organizer=env[0], name='MRMCD2017', slug='2017',
        date_from=datetime(now().year + 1, 9, 1, tzinfo=UTC),
        live=True, is_public=True, has_subevents=True
    )
    with scopes_disabled():
        se1 = e.subevents.create(date_from=now(), name='SE1', active=True)

    prop = env[0].meta_properties.create(name='loc', default='HH')
    e0.meta_values.create(value='MA', property=prop)
    propval = se1.meta_values.create(value='HD', property=prop)
    r = client.get('/mrmcd/events/ical/?attr[loc]=HD')
    assert b'SE1' in r.content
    assert b'DS2017' not in r.content
    r = client.get('/mrmcd/events/ical/?attr[loc]=MA')
    assert b'SE1' not in r.content
    assert b'DS2017' in r.content

    r = client.get('/mrmcd/events/ical/?attr[loc]=HH')
    assert b'SE1' not in r.content
    propval.delete()
    r = client.get('/mrmcd/events/ical/?attr[loc]=HH')
    assert b'SE1' in r.content
    e.meta_values.create(value='B', property=prop)
    r = client.get('/mrmcd/events/ical/?attr[loc]=HH')
    assert b'SE1' not in r.content
    r = client.get('/mrmcd/events/ical/?attr[loc]=B')
    assert b'SE1' in r.content
