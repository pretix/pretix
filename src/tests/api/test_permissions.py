import time

import pytest
from django.test import override_settings

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
    'subevents/',
    'taxrules/',
    'waitinglistentries/',
    'checkinlists/',
]

event_permission_urls = [
    ('get', 'can_view_orders', 'orders/', 200),
    ('get', 'can_view_orders', 'orderpositions/', 200),
    ('get', 'can_view_vouchers', 'vouchers/', 200),
    ('get', 'can_view_orders', 'invoices/', 200),
    ('get', 'can_view_orders', 'waitinglistentries/', 200),
    ('get', 'can_change_items', 'categories/', 200),
    ('get', 'can_change_items', 'items/', 200),
    ('get', 'can_change_items', 'questions/', 200),
    ('get', 'can_change_items', 'quotas/', 200),
    ('post', 'can_change_event_settings', 'taxrules/', 400),
    ('put', 'can_change_event_settings', 'taxrules/1/', 404),
    ('patch', 'can_change_event_settings', 'taxrules/1/', 404),
    ('delete', 'can_change_event_settings', 'taxrules/1/', 404),
    ('post', 'can_change_vouchers', 'vouchers/', 400),
    ('put', 'can_change_vouchers', 'vouchers/1/', 404),
    ('patch', 'can_change_vouchers', 'vouchers/1/', 404),
    ('delete', 'can_change_vouchers', 'vouchers/1/', 404),
    ('post', 'can_change_items', 'quotas/', 400),
    ('put', 'can_change_items', 'quotas/1/', 404),
    ('patch', 'can_change_items', 'quotas/1/', 404),
    ('delete', 'can_change_items', 'quotas/1/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/mark_paid/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/mark_pending/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/mark_expired/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/mark_canceled/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/extend/', 400),
    ('get', 'can_view_orders', 'checkinlists/', 200),
    ('post', 'can_change_event_settings', 'checkinlists/', 400),
    ('put', 'can_change_event_settings', 'checkinlists/1/', 404),
    ('patch', 'can_change_event_settings', 'checkinlists/1/', 404),
    ('delete', 'can_change_event_settings', 'checkinlists/1/', 404),
]


@pytest.fixture
def token_client(client, team):
    team.can_view_orders = True
    team.can_view_vouchers = True
    team.can_change_items = True
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
    if urlset[3] == 404:
        assert resp.status_code == 403
    else:
        assert resp.status_code in (404, 403)


@pytest.mark.django_db
def test_log_out_after_absolute_timeout(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = False
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 12 - 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 403


@pytest.mark.django_db
def test_dont_logout_before_absolute_timeout(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = True
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 12 + 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 200


@pytest.mark.django_db
@override_settings(PRETIX_LONG_SESSIONS=False)
def test_ignore_long_session_if_disabled_in_config(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = True
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 12 - 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 403


@pytest.mark.django_db
def test_dont_logout_in_long_session(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = True
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 12 - 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 200


@pytest.mark.django_db
def test_log_out_after_relative_timeout(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = False
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 6
    session['pretix_auth_last_used'] = int(time.time()) - 3600 * 3 - 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 403


@pytest.mark.django_db
def test_dont_logout_before_relative_timeout(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = True
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 6
    session['pretix_auth_last_used'] = int(time.time()) - 3600 * 3 + 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 200


@pytest.mark.django_db
def test_dont_logout_by_relative_in_long_session(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = True
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 5
    session['pretix_auth_last_used'] = int(time.time()) - 3600 * 3 - 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 200


@pytest.mark.django_db
def test_update_session_activity(user_client, team, organizer, event):
    t1 = int(time.time()) - 5
    session = user_client.session
    session['pretix_auth_long_session'] = False
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 5
    session['pretix_auth_last_used'] = t1
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 200

    assert user_client.session['pretix_auth_last_used'] > t1
