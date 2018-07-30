import pytest
from django.conf import settings
from django.utils.timezone import now

from pretix.base.models import Event, Organizer


@pytest.fixture
def event():
    o = Organizer.objects.create(name='MRMCD', slug='mrmcd')
    event = Event.objects.create(
        organizer=o, name='MRMCD2015', slug='2015',
        date_from=now(),
    )
    settings.SITE_URL = 'http://example.com'
    return event


@pytest.mark.django_db
def test_require_plugin(event, client):
    event.plugins = 'pretix.plugins.paypal'
    event.live = True
    event.save()
    r = client.get('/mrmcd/2015/paypal/abort/', follow=False)
    assert r.status_code == 302
    event.plugins = ''
    event.save()
    r = client.get('/mrmcd/2015/paypal/abort/', follow=False)
    assert r.status_code == 404


@pytest.mark.django_db
def test_require_live(event, client):
    event.plugins = 'pretix.plugins.paypal'
    event.live = True
    event.save()
    r = client.get('/mrmcd/2015/paypal/abort/', follow=False)
    assert r.status_code == 302
    r = client.get('/mrmcd/2015/paypal/webhook/', follow=False)
    assert r.status_code == 405

    event.live = False
    event.save()
    r = client.get('/mrmcd/2015/paypal/abort/', follow=False)
    assert r.status_code == 403
    r = client.get('/mrmcd/2015/paypal/webhook/', follow=False)
    assert r.status_code == 405
