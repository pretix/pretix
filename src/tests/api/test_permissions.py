import pytest

from pretix.base.models import Organizer

event_urls = [
    'categories/',
    'invoices/',
    'items/',
    'orders/',
    'orderpositions/',
    'questions/',
    'quotas/',
    'vouchers/',
    'waitinglistentries/',
]

event_permission_urls = [
    ('get', 'can_view_orders', 'orders/', 200),
    ('get', 'can_view_orders', 'orderpositions/', 200),
    ('get', 'can_view_vouchers', 'vouchers/', 200),
    ('get', 'can_view_orders', 'invoices/', 200),
    ('get', 'can_view_orders', 'waitinglistentries/', 200),
]


@pytest.fixture
def token_client(client, team):
    team.can_view_orders = True
    team.can_view_vouchers = True
    team.save()
    t = team.tokens.create(name='Foo')
    client.credentials(HTTP_AUTHORIZATION='Token ' + t.token)
    return client


@pytest.mark.django_db
def test_organizer_allowed(token_client, organizer):
    resp = token_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_organizer_not_allowed(token_client, organizer):
    o2 = Organizer.objects.create(slug='o2', name='Organizer 2')
    resp = token_client.get('/api/v1/organizers/{}/events/'.format(o2.slug))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_organizer_not_existing(token_client, organizer):
    resp = token_client.get('/api/v1/organizers/{}/events/'.format('o2'))
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_allowed_all_events(token_client, team, organizer, event, url):
    team.all_events = True
    team.save()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url))
    assert resp.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_allowed_limit_events(token_client, organizer, team, event, url):
    team.all_events = False
    team.save()
    team.limit_events.add(event)
    resp = token_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url))
    assert resp.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_not_allowed(token_client, organizer, team, event, url):
    team.all_events = False
    team.save()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url))
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_not_existing(token_client, organizer, url, event):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url))
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", event_permission_urls)
def test_token_event_permission_allowed(token_client, team, organizer, event, urlset):
    team.all_events = True
    setattr(team, urlset[1], True)
    team.save()
    resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/{}/{}'.format(
        organizer.slug, event.slug, urlset[2]))
    assert resp.status_code == urlset[3]


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", event_permission_urls)
def test_token_event_permission_not_allowed(token_client, team, organizer, event, urlset):
    team.all_events = True
    setattr(team, urlset[1], False)
    team.save()
    resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/{}/{}'.format(
        organizer.slug, event.slug, urlset[2]))
    assert resp.status_code in (404, 403)
