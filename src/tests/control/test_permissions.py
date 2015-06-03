from datetime import timedelta

from django.utils.timezone import now
import pytest
from pretix.base.models import Event, Organizer, User, EventPermission, Order


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy@dummy.dummy', 'dummy')
    Order.objects.create(
        code='FOO', event=event,
        user=user, status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0, payment_provider='banktransfer'
    )
    return event, user


event_urls = [
    "",
    "settings/",
    "settings/plugins",
    "settings/payment",
    "settings/tickets",
    "items/",
    "items/add",
    "items/abc/",
    "items/abc/variations",
    "items/abc/restrictions",
    "categories/",
    "categories/add",
    "categories/abc/",
    "categories/abc/up",
    "categories/abc/down",
    "categories/abc/delete",
    "questions/",
    "questions/abc/delete",
    "questions/abc/",
    "questions/add",
    "properties/",
    "properties/abc/delete",
    "properties/abc/",
    "properties/add",
    "quotas/",
    "quotas/abc/delete",
    "quotas/abc/",
    "quotas/add",
    "orders/ABC/transition",
    "orders/ABC/extend",
    "orders/ABC/",
    "orders/",
]


@pytest.mark.django_db
@pytest.mark.parametrize("url", [
    "",
    "settings",
    "organizers/",
    "organizers/add",
    "organizer/dummy/edit",
    "events/",
    "events/add",
    "event/dummy/add",
] + ['event/dummy/dummy/' + u for u in event_urls])
def test_logged_out(client, env, url):
    client.logout()
    response = client.get('/control/' + url)
    assert response.status_code == 302
    assert "/control/login" in response['Location']


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_wrong_event(client, env, url):
    client.login(identifier='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/' + url)
    # These permission violations do not yield a 403 error, but
    # a 404 error to prevent information leakage
    assert response.status_code == 404


event_permission_urls = [
    ("can_change_settings", "settings/", 200),
    ("can_change_settings", "settings/plugins", 200),
    ("can_change_settings", "settings/payment", 200),
    ("can_change_settings", "settings/tickets", 200),
    # Lists are currently not access-controlled
    # ("can_change_items", "items/", 200),
    ("can_change_items", "items/add", 200),
    # ("can_change_items", "categories/", 200),
    # We don't have to create categories and similar objects
    # for testing this, it is enough to test that a 404 error
    # is returned instead of a 403 one.
    ("can_change_items", "categories/abc/", 404),
    ("can_change_items", "categories/abc/delete", 404),
    ("can_change_items", "categories/add", 200),
    # ("can_change_items", "questions/", 200),
    ("can_change_items", "questions/abc/", 404),
    ("can_change_items", "questions/abc/delete", 404),
    ("can_change_items", "questions/add", 200),
    # ("can_change_items", "properties/", 200),
    ("can_change_items", "properties/abc/", 404),
    ("can_change_items", "properties/abc/delete", 404),
    ("can_change_items", "properties/add", 200),
    # ("can_change_items", "quotas/", 200),
    ("can_change_items", "quotas/abc/", 404),
    ("can_change_items", "quotas/abc/delete", 404),
    ("can_change_items", "quotas/add", 200),
    ("can_view_orders", "orders/overview/", 200),
    ("can_view_orders", "orders/", 200),
    ("can_view_orders", "orders/FOO/", 200),
    ("can_change_orders", "orders/FOO/extend", 200),
    ("can_change_orders", "orders/FOO/transition", 405),
]


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code", event_permission_urls)
def test_wrong_event_permission(client, env, perm, url, code):
    ep = EventPermission(
        event=env[0], user=env[1],
    )
    setattr(ep, perm, False)
    ep.save()
    client.login(identifier='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/' + url)
    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code", event_permission_urls)
def test_correct_event_permission(client, env, perm, url, code):
    ep = EventPermission(
        event=env[0], user=env[1],
    )
    setattr(ep, perm, True)
    ep.save()
    client.login(identifier='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/' + url)
    assert response.status_code == code
