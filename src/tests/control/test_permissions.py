import time
from datetime import timedelta

import pytest
from django.utils.timezone import now

from pretix.base.models import Event, Order, Organizer, Team, User


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    Order.objects.create(
        code='FOO', event=event,
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0,
    )
    Team.objects.create(pk=1, organizer=o)
    return event, user, o


superuser_urls = [
    "global/settings/",
    "logdetail/",
    "logdetail/payment/",
    "logdetail/refund/",
    "users/select2",
    "users/",
    "users/add",
    "users/1/",
    "users/1/impersonate",
    "users/1/reset",
    "sudo/sessions/",
]


staff_urls = [
    "global/update/",
    "sudo/",
    "sudo/2/",
]

event_urls = [
    "",
    "comment/",
    "live/",
    "delete/",
    "dangerzone/",
    "cancel/",
    "settings/",
    "settings/plugins",
    "settings/payment",
    "settings/tickets",
    "settings/email",
    "settings/cancel",
    "settings/invoice",
    "settings/invoice/preview",
    "settings/widget",
    "settings/tax/",
    "settings/tax/add",
    "settings/tax/1/",
    "settings/tax/1/delete",
    "items/",
    "items/add",
    "items/1/",
    "items/1/up",
    "items/1/down",
    "items/1/delete",
    "categories/",
    "categories/add",
    "categories/2/",
    "categories/2/up",
    "categories/2/down",
    "categories/2/delete",
    "questions/",
    "questions/2/delete",
    "questions/2/",
    "questions/add",
    "vouchers/",
    "vouchers/2/delete",
    "vouchers/2/",
    "vouchers/add",
    "vouchers/bulk_add",
    "vouchers/rng",
    "subevents/",
    "subevents/select2",
    "subevents/add",
    "subevents/2/delete",
    "subevents/2/",
    "quotas/",
    "quotas/2/delete",
    "quotas/2/change",
    "quotas/2/",
    "quotas/add",
    "orders/ABC/transition",
    "orders/ABC/resend",
    "orders/ABC/invoice",
    "orders/ABC/extend",
    "orders/ABC/reactivate",
    "orders/ABC/change",
    "orders/ABC/contact",
    "orders/ABC/comment",
    "orders/ABC/locale",
    "orders/ABC/approve",
    "orders/ABC/deny",
    "orders/ABC/checkvatid",
    "orders/ABC/cancellationrequests/1/delete",
    "orders/ABC/payments/1/cancel",
    "orders/ABC/payments/1/confirm",
    "orders/ABC/refund",
    "orders/ABC/refunds/1/cancel",
    "orders/ABC/refunds/1/process",
    "orders/ABC/refunds/1/done",
    "orders/ABC/delete",
    "orders/ABC/",
    "orders/",
    "orders/import/",
    "checkinlists/",
    "checkinlists/1/",
    "checkinlists/1/change",
    "checkinlists/1/delete",
    "waitinglist/",
    "waitinglist/auto_assign",
    "invoice/1",
]

organizer_urls = [
    'organizer/abc/edit',
    'organizer/abc/',
    'organizer/abc/teams',
    'organizer/abc/team/1/',
    'organizer/abc/team/1/edit',
    'organizer/abc/team/1/delete',
    'organizer/abc/team/add',
    'organizer/abc/devices',
    'organizer/abc/device/add',
    'organizer/abc/device/1/edit',
    'organizer/abc/device/1/connect',
    'organizer/abc/device/1/revoke',
    'organizer/abc/webhooks',
    'organizer/abc/webhook/add',
    'organizer/abc/webhook/1/edit',
    'organizer/abc/webhook/1/logs',
    'organizer/abc/giftcards',
    'organizer/abc/giftcard/add',
    'organizer/abc/giftcard/1/',
]


@pytest.fixture
def perf_patch(monkeypatch):
    # Patch out template rendering for performance improvements
    monkeypatch.setattr("django.template.backends.django.Template.render", lambda *args, **kwargs: "mocked template")


@pytest.mark.django_db
@pytest.mark.parametrize("url", [
    "",
    "settings",
    "admin/",
    "organizers/",
    "organizers/add",
    "organizers/select2",
    "events/",
    "events/add",
] + ['event/dummy/dummy/' + u for u in event_urls] + organizer_urls)
def test_logged_out(client, env, url):
    client.logout()
    response = client.get('/control/' + url)
    assert response.status_code == 302
    assert "/control/login" in response['Location']


@pytest.mark.django_db
@pytest.mark.parametrize("url", superuser_urls)
def test_superuser_required(perf_patch, client, env, url):
    client.login(email='dummy@dummy.dummy', password='dummy')
    env[1].is_staff = True
    env[1].save()
    response = client.get('/control/' + url)
    if response.status_code == 302:
        assert '/sudo/' in response['Location']
    else:
        assert response.status_code == 403
    env[1].staffsession_set.create(date_start=now(), session_key=client.session.session_key)
    response = client.get('/control/' + url)
    assert response.status_code in (200, 302, 404)


@pytest.mark.django_db
@pytest.mark.parametrize("url", staff_urls)
def test_staff_required(perf_patch, client, env, url):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/' + url)
    assert response.status_code == 403
    env[1].is_staff = True
    env[1].save()
    response = client.get('/control/' + url)
    assert response.status_code in (200, 302, 404)


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_wrong_event(perf_patch, client, env, url):
    event2 = Event.objects.create(
        organizer=env[2], name='Dummy', slug='dummy2',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    t = Team.objects.create(organizer=env[2], can_change_event_settings=True)
    t.members.add(env[1])
    t.limit_events.add(event2)

    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/' + url)
    # These permission violations do not yield a 403 error, but
    # a 404 error to prevent information leakage
    assert response.status_code == 404


event_permission_urls = [
    ("can_change_event_settings", "live/", 200),
    ("can_change_event_settings", "delete/", 200),
    ("can_change_event_settings", "dangerzone/", 200),
    ("can_change_event_settings", "settings/", 200),
    ("can_change_event_settings", "settings/plugins", 200),
    ("can_change_event_settings", "settings/payment", 200),
    ("can_change_event_settings", "settings/tickets", 200),
    ("can_change_event_settings", "settings/email", 200),
    ("can_change_event_settings", "settings/cancel", 200),
    ("can_change_event_settings", "settings/invoice", 200),
    ("can_change_event_settings", "settings/widget", 200),
    ("can_change_event_settings", "settings/invoice/preview", 200),
    ("can_change_event_settings", "settings/tax/", 200),
    ("can_change_event_settings", "settings/tax/1/", 404),
    ("can_change_event_settings", "settings/tax/add", 200),
    ("can_change_event_settings", "settings/tax/1/delete", 404),
    ("can_change_event_settings", "comment/", 405),
    # Lists are currently not access-controlled
    # ("can_change_items", "items/", 200),
    ("can_change_items", "items/add", 200),
    ("can_change_items", "items/1/up", 404),
    ("can_change_items", "items/1/down", 404),
    ("can_change_items", "items/1/delete", 404),
    # ("can_change_items", "categories/", 200),
    # We don't have to create categories and similar objects
    # for testing this, it is enough to test that a 404 error
    # is returned instead of a 403 one.
    ("can_change_items", "categories/2/", 404),
    ("can_change_items", "categories/2/delete", 404),
    ("can_change_items", "categories/2/up", 404),
    ("can_change_items", "categories/2/down", 404),
    ("can_change_items", "categories/add", 200),
    # ("can_change_items", "questions/", 200),
    ("can_change_items", "questions/2/", 404),
    ("can_change_items", "questions/2/delete", 404),
    ("can_change_items", "questions/2/up", 404),
    ("can_change_items", "questions/2/down", 404),
    ("can_change_items", "questions/reorder", 400),
    ("can_change_items", "questions/add", 200),
    # ("can_change_items", "quotas/", 200),
    ("can_change_items", "quotas/2/change", 404),
    ("can_change_items", "quotas/2/delete", 404),
    ("can_change_items", "quotas/add", 200),
    ("can_change_event_settings", "subevents/", 200),
    ("can_change_event_settings", "subevents/2/", 404),
    ("can_change_event_settings", "subevents/2/delete", 404),
    ("can_change_event_settings", "subevents/add", 200),
    ("can_view_orders", "orders/overview/", 200),
    ("can_view_orders", "orders/export/", 200),
    ("can_view_orders", "orders/", 200),
    ("can_view_orders", "orders/FOO/", 200),
    ("can_change_orders", "orders/FOO/extend", 200),
    ("can_change_orders", "orders/FOO/reactivate", 302),
    ("can_change_orders", "orders/FOO/contact", 200),
    ("can_change_orders", "orders/FOO/transition", 405),
    ("can_change_orders", "orders/FOO/checkvatid", 405),
    ("can_change_orders", "orders/FOO/resend", 405),
    ("can_change_orders", "orders/FOO/invoice", 405),
    ("can_change_orders", "orders/FOO/change", 200),
    ("can_change_orders", "orders/FOO/approve", 200),
    ("can_change_orders", "orders/FOO/deny", 200),
    ("can_change_orders", "orders/FOO/delete", 302),
    ("can_change_orders", "orders/FOO/comment", 405),
    ("can_change_orders", "orders/FOO/locale", 200),
    ("can_change_orders", "orders/import/", 200),
    ("can_change_orders", "orders/import/0ab7b081-92d3-4480-82de-2f8b056fd32f/", 404),
    ("can_view_orders", "orders/FOO/answer/5/", 404),
    ("can_change_orders", "cancel/", 200),
    ("can_change_vouchers", "vouchers/add", 200),
    ("can_change_orders", "requiredactions/", 200),
    ("can_change_vouchers", "vouchers/bulk_add", 200),
    ("can_view_vouchers", "vouchers/", 200),
    ("can_view_vouchers", "vouchers/tags/", 200),
    ("can_change_vouchers", "vouchers/1234/", 404),
    ("can_change_vouchers", "vouchers/1234/delete", 404),
    ("can_view_orders", "waitinglist/", 200),
    ("can_change_orders", "waitinglist/auto_assign", 405),
    ("can_view_orders", "checkinlists/", 200),
    ("can_view_orders", "checkinlists/1/", 404),
    ("can_change_event_settings", "checkinlists/add", 200),
    ("can_change_event_settings", "checkinlists/1/change", 404),
    ("can_change_event_settings", "checkinlists/1/delete", 404),
]


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code", event_permission_urls)
def test_wrong_event_permission(perf_patch, client, env, perm, url, code):
    t = Team(
        organizer=env[2], all_events=True
    )
    setattr(t, perm, False)
    t.save()
    t.members.add(env[1])
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/' + url)
    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code", event_permission_urls)
def test_limited_event_permission_for_other_event(perf_patch, client, env, perm, url, code):
    event2 = Event.objects.create(
        organizer=env[2], name='Dummy', slug='dummy2',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    t = Team.objects.create(organizer=env[2], can_change_event_settings=True)
    t.members.add(env[1])
    t.limit_events.add(event2)

    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/' + url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_current_permission(client, env):
    t = Team(
        organizer=env[2], all_events=True
    )
    setattr(t, 'can_change_event_settings', True)
    t.save()
    t.members.add(env[1])

    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/settings/')
    assert response.status_code == 200
    setattr(t, 'can_change_event_settings', False)
    t.save()
    response = client.get('/control/event/dummy/dummy/settings/')
    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code", event_permission_urls)
def test_correct_event_permission_all_events(perf_patch, client, env, perm, url, code):
    t = Team(organizer=env[2], all_events=True)
    setattr(t, perm, True)
    t.save()
    t.members.add(env[1])
    client.login(email='dummy@dummy.dummy', password='dummy')
    session = client.session
    session['pretix_auth_login_time'] = int(time.time())
    session.save()
    response = client.get('/control/event/dummy/dummy/' + url)
    assert response.status_code == code


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code", event_permission_urls)
def test_correct_event_permission_limited(perf_patch, client, env, perm, url, code):
    t = Team(organizer=env[2])
    setattr(t, perm, True)
    t.save()
    t.members.add(env[1])
    t.limit_events.add(env[0])
    client.login(email='dummy@dummy.dummy', password='dummy')
    session = client.session
    session['pretix_auth_login_time'] = int(time.time())
    session.save()
    response = client.get('/control/event/dummy/dummy/' + url)
    assert response.status_code == code


@pytest.mark.django_db
@pytest.mark.parametrize("url", organizer_urls)
def test_wrong_organizer(perf_patch, client, env, url):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/' + url)
    # These permission violations do not yield a 403 error, but
    # a 404 error to prevent information leakage
    assert response.status_code == 404


organizer_permission_urls = [
    ("can_change_teams", "organizer/dummy/teams", 200),
    ("can_change_teams", "organizer/dummy/team/add", 200),
    ("can_change_teams", "organizer/dummy/team/1/", 200),
    ("can_change_teams", "organizer/dummy/team/1/edit", 200),
    ("can_change_teams", "organizer/dummy/team/1/delete", 200),
    ("can_change_organizer_settings", "organizer/dummy/edit", 200),
    ("can_change_organizer_settings", "organizer/dummy/devices", 200),
    ("can_change_organizer_settings", "organizer/dummy/device/add", 200),
    ("can_change_organizer_settings", "organizer/dummy/device/1/edit", 404),
    ("can_change_organizer_settings", "organizer/dummy/device/1/connect", 404),
    ("can_change_organizer_settings", "organizer/dummy/device/1/revoke", 404),
    ("can_manage_gift_cards", "organizer/dummy/giftcards", 200),
    ("can_manage_gift_cards", "organizer/dummy/giftcard/add", 200),
    ("can_manage_gift_cards", "organizer/dummy/giftcard/1/", 404),
]


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code", organizer_permission_urls)
def test_wrong_organizer_permission(perf_patch, client, env, perm, url, code):
    t = Team(organizer=env[2])
    setattr(t, perm, False)
    t.save()
    t.members.add(env[1])
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/' + url)
    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code", organizer_permission_urls)
def test_correct_organizer_permission(perf_patch, client, env, perm, url, code):
    t = Team(organizer=env[2])
    setattr(t, perm, True)
    t.save()
    t.members.add(env[1])
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.session['pretix_auth_login_time'] = int(time.time())
    client.session.save()
    response = client.get('/control/' + url)
    assert response.status_code == code
