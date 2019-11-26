import time

import pytest
from django.test import override_settings
from django.utils.timezone import now

from pretix.base.models import Organizer

event_urls = [
    (None, ''),
    (None, 'categories/'),
    ('can_view_orders', 'invoices/'),
    (None, 'items/'),
    ('can_view_orders', 'orders/'),
    ('can_view_orders', 'orderpositions/'),
    (None, 'questions/'),
    (None, 'quotas/'),
    ('can_view_vouchers', 'vouchers/'),
    (None, 'subevents/'),
    (None, 'taxrules/'),
    ('can_view_orders', 'waitinglistentries/'),
    ('can_view_orders', 'checkinlists/'),
]

event_permission_sub_urls = [
    ('get', 'can_view_orders', 'orders/', 200),
    ('get', 'can_view_orders', 'orderpositions/', 200),
    ('delete', 'can_change_orders', 'orderpositions/1/', 404),
    ('post', 'can_change_orders', 'orderpositions/1/price_calc/', 404),
    ('get', 'can_view_vouchers', 'vouchers/', 200),
    ('get', 'can_view_orders', 'invoices/', 200),
    ('get', 'can_view_orders', 'invoices/1/', 404),
    ('post', 'can_change_orders', 'invoices/1/regenerate/', 404),
    ('post', 'can_change_orders', 'invoices/1/reissue/', 404),
    ('get', 'can_view_orders', 'waitinglistentries/', 200),
    ('get', 'can_view_orders', 'waitinglistentries/1/', 404),
    ('post', 'can_change_orders', 'waitinglistentries/', 400),
    ('delete', 'can_change_orders', 'waitinglistentries/1/', 404),
    ('patch', 'can_change_orders', 'waitinglistentries/1/', 404),
    ('put', 'can_change_orders', 'waitinglistentries/1/', 404),
    ('post', 'can_change_orders', 'waitinglistentries/1/send_voucher/', 404),
    ('get', None, 'categories/', 200),
    ('get', None, 'items/', 200),
    ('get', None, 'questions/', 200),
    ('get', None, 'quotas/', 200),
    ('post', 'can_change_items', 'items/', 400),
    ('get', None, 'items/1/', 404),
    ('put', 'can_change_items', 'items/1/', 404),
    ('patch', 'can_change_items', 'items/1/', 404),
    ('delete', 'can_change_items', 'items/1/', 404),
    ('post', 'can_change_items', 'categories/', 400),
    ('get', None, 'categories/1/', 404),
    ('put', 'can_change_items', 'categories/1/', 404),
    ('patch', 'can_change_items', 'categories/1/', 404),
    ('delete', 'can_change_items', 'categories/1/', 404),
    ('post', 'can_change_items', 'items/1/variations/', 404),
    ('get', None, 'items/1/variations/', 404),
    ('get', None, 'items/1/variations/1/', 404),
    ('put', 'can_change_items', 'items/1/variations/1/', 404),
    ('patch', 'can_change_items', 'items/1/variations/1/', 404),
    ('delete', 'can_change_items', 'items/1/variations/1/', 404),
    ('get', None, 'items/1/addons/', 404),
    ('get', None, 'items/1/addons/1/', 404),
    ('post', 'can_change_items', 'items/1/addons/', 404),
    ('put', 'can_change_items', 'items/1/addons/1/', 404),
    ('patch', 'can_change_items', 'items/1/addons/1/', 404),
    ('delete', 'can_change_items', 'items/1/addons/1/', 404),
    ('get', None, 'subevents/', 200),
    ('get', None, 'subevents/1/', 404),
    ('get', None, 'taxrules/', 200),
    ('get', None, 'taxrules/1/', 404),
    ('post', 'can_change_event_settings', 'taxrules/', 400),
    ('put', 'can_change_event_settings', 'taxrules/1/', 404),
    ('patch', 'can_change_event_settings', 'taxrules/1/', 404),
    ('delete', 'can_change_event_settings', 'taxrules/1/', 404),
    ('get', 'can_view_vouchers', 'vouchers/', 200),
    ('get', 'can_view_vouchers', 'vouchers/1/', 404),
    ('post', 'can_change_vouchers', 'vouchers/', 201),
    ('put', 'can_change_vouchers', 'vouchers/1/', 404),
    ('patch', 'can_change_vouchers', 'vouchers/1/', 404),
    ('delete', 'can_change_vouchers', 'vouchers/1/', 404),
    ('get', None, 'quotas/', 200),
    ('get', None, 'quotas/1/', 404),
    ('post', 'can_change_items', 'quotas/', 400),
    ('put', 'can_change_items', 'quotas/1/', 404),
    ('patch', 'can_change_items', 'quotas/1/', 404),
    ('delete', 'can_change_items', 'quotas/1/', 404),
    ('get', None, 'questions/', 200),
    ('get', None, 'questions/1/', 404),
    ('post', 'can_change_items', 'questions/', 400),
    ('put', 'can_change_items', 'questions/1/', 404),
    ('patch', 'can_change_items', 'questions/1/', 404),
    ('delete', 'can_change_items', 'questions/1/', 404),
    ('get', None, 'questions/1/options/', 404),
    ('get', None, 'questions/1/options/1/', 404),
    ('put', 'can_change_items', 'questions/1/options/1/', 404),
    ('patch', 'can_change_items', 'questions/1/options/1/', 404),
    ('delete', 'can_change_items', 'questions/1/options/1/', 404),
    ('post', 'can_change_orders', 'orders/', 400),
    ('patch', 'can_change_orders', 'orders/ABC12/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/mark_paid/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/mark_pending/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/mark_expired/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/mark_canceled/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/approve/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/deny/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/extend/', 400),
    ('post', 'can_change_orders', 'orders/ABC12/create_invoice/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/resend_link/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/regenerate_secrets/', 404),
    ('get', 'can_view_orders', 'orders/ABC12/payments/', 404),
    ('get', 'can_view_orders', 'orders/ABC12/payments/1/', 404),
    ('get', 'can_view_orders', 'orders/ABC12/refunds/', 404),
    ('get', 'can_view_orders', 'orders/ABC12/refunds/1/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/payments/1/confirm/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/payments/1/refund/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/payments/1/cancel/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/refunds/1/cancel/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/refunds/1/process/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/refunds/1/done/', 404),
    ('get', 'can_view_orders', 'checkinlists/', 200),
    ('post', 'can_change_event_settings', 'checkinlists/', 400),
    ('put', 'can_change_event_settings', 'checkinlists/1/', 404),
    ('patch', 'can_change_event_settings', 'checkinlists/1/', 404),
    ('delete', 'can_change_event_settings', 'checkinlists/1/', 404),
    ('post', 'can_create_events', 'clone/', 400),
    ('get', 'can_view_orders', 'cartpositions/', 200),
    ('get', 'can_view_orders', 'cartpositions/1/', 404),
    ('post', 'can_change_orders', 'cartpositions/', 400),
    ('delete', 'can_change_orders', 'cartpositions/1/', 404),
]

org_permission_sub_urls = [
    ('get', 'can_change_organizer_settings', 'webhooks/', 200),
    ('post', 'can_change_organizer_settings', 'webhooks/', 400),
    ('get', 'can_change_organizer_settings', 'webhooks/1/', 404),
    ('put', 'can_change_organizer_settings', 'webhooks/1/', 404),
    ('patch', 'can_change_organizer_settings', 'webhooks/1/', 404),
    ('delete', 'can_change_organizer_settings', 'webhooks/1/', 404),
    ('get', 'can_manage_gift_cards', 'giftcards/', 200),
    ('post', 'can_manage_gift_cards', 'giftcards/', 400),
    ('get', 'can_manage_gift_cards', 'giftcards/1/', 404),
    ('put', 'can_manage_gift_cards', 'giftcards/1/', 404),
    ('patch', 'can_manage_gift_cards', 'giftcards/1/', 404),
]


event_permission_root_urls = [
    ('post', 'can_create_events', 400),
    ('put', 'can_change_event_settings', 400),
    ('patch', 'can_change_event_settings', 200),
    ('delete', 'can_change_event_settings', 204),
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
def test_organizer_not_allowed_device(device_client, organizer):
    o2 = Organizer.objects.create(slug='o2', name='Organizer 2')
    resp = device_client.get('/api/v1/organizers/{}/events/'.format(o2.slug))
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
    resp = token_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_allowed_all_events_device(device_client, device, organizer, event, url):
    resp = device_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    if url[0] is None or url[0] in device.permission_set():
        assert resp.status_code == 200
    else:
        assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_allowed_limit_events(token_client, organizer, team, event, url):
    team.all_events = False
    team.save()
    team.limit_events.add(event)
    resp = token_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_allowed_limit_events_device(device_client, organizer, device, event, url):
    device.all_events = False
    device.save()
    device.limit_events.add(event)
    resp = device_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    if url[0] is None or url[0] in device.permission_set():
        assert resp.status_code == 200
    else:
        assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_not_allowed(token_client, organizer, team, event, url):
    team.all_events = False
    team.save()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_not_allowed_device(device_client, organizer, device, event, url):
    device.all_events = False
    device.save()
    resp = device_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_not_existing(token_client, organizer, url, event):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", event_permission_sub_urls)
def test_token_event_subresources_permission_allowed(token_client, team, organizer, event, urlset):
    team.all_events = True
    if urlset[1]:
        setattr(team, urlset[1], True)
    team.save()
    resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/{}/{}'.format(
        organizer.slug, event.slug, urlset[2]))
    assert resp.status_code == urlset[3]


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", event_permission_sub_urls)
def test_token_event_subresources_permission_not_allowed(token_client, team, organizer, event, urlset):
    if urlset[1] is None:
        team.all_events = False
    else:
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
@pytest.mark.parametrize("urlset", event_permission_root_urls)
def test_token_event_permission_allowed(token_client, team, organizer, event, urlset):
    team.all_events = True
    setattr(team, urlset[1], True)
    team.save()
    if urlset[0] == 'post':
        resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/'.format(organizer.slug))
    else:
        resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug))
    assert resp.status_code == urlset[2]


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", event_permission_root_urls)
def test_token_event_permission_not_allowed(token_client, team, organizer, event, urlset):
    team.all_events = True
    setattr(team, urlset[1], False)
    team.save()
    if urlset[0] == 'post':
        resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/'.format(organizer.slug))
    else:
        resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug))
    assert resp.status_code == 403


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


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", event_permission_sub_urls)
def test_device_subresource_permission_check(device_client, device, organizer, event, urlset):
    resp = getattr(device_client, urlset[0])('/api/v1/organizers/{}/events/{}/{}'.format(
        organizer.slug, event.slug, urlset[2]))
    if urlset[1] is None or urlset[1] in device.permission_set():
        assert resp.status_code == urlset[3]
    else:
        if urlset[3] == 404:
            assert resp.status_code == 403
        else:
            assert resp.status_code in (404, 403)


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", org_permission_sub_urls)
def test_token_org_subresources_permission_allowed(token_client, team, organizer, event, urlset):
    team.all_events = True
    if urlset[1]:
        setattr(team, urlset[1], True)
    team.save()
    resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/{}'.format(
        organizer.slug, urlset[2]))
    assert resp.status_code == urlset[3]


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", org_permission_sub_urls)
def test_token_org_subresources_permission_not_allowed(token_client, team, organizer, event, urlset):
    if urlset[1] is None:
        team.all_events = False
    else:
        team.all_events = True
        setattr(team, urlset[1], False)
    team.save()
    resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/{}'.format(
        organizer.slug, urlset[2]))
    if urlset[3] == 404:
        assert resp.status_code == 403
    else:
        assert resp.status_code in (404, 403)


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_staff_requires_staff_session(user_client, organizer, team, event, url, user):
    team.delete()
    user.is_staff = True
    user.save()

    resp = user_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 403
    user.staffsession_set.create(date_start=now(), session_key=user_client.session.session_key)
    resp = user_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 200
