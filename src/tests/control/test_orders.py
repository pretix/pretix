from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now

from pretix.base.models import (
    CachedTicket, Event, EventPermission, Item, Order, OrderPosition,
    Organizer, Quota, User,
)


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,tests.testdummy'
    )
    event.settings.set('ticketoutput_testdummy__enabled', True)
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    EventPermission.objects.create(
        event=event,
        user=user,
        can_view_orders=True,
        can_change_orders=True
    )
    o = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0, payment_provider='banktransfer'
    )
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 category=None, default_price=23,
                                 admission=True)
    event.settings.set('attendee_names_asked', True)
    OrderPosition.objects.create(
        order=o,
        item=ticket,
        variation=None,
        price=Decimal("14"),
        attendee_name="Peter"
    )
    return event, user, o, ticket


@pytest.mark.django_db
def test_order_list(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?user=peter')
    assert 'FOO' not in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?user=dummy')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?status=p')
    assert 'FOO' not in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?status=n')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?item=15')
    assert 'FOO' not in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?item=%s' % env[3].id)
    assert 'FOO' in response.rendered_content


@pytest.mark.django_db
def test_order_detail(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/')
    assert 'Early-bird' in response.rendered_content
    assert 'Peter' in response.rendered_content


@pytest.mark.django_db
def test_order_transition_to_paid_in_time_success(client, env):
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'p'
    })
    o = Order.objects.get(id=env[2].id)
    assert o.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_transition_to_paid_expired_quota_left(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_EXPIRED
    o.save()
    q = Quota.objects.create(event=env[0], size=10)
    q.items.add(env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    res = client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'p'
    })
    o = Order.objects.get(id=env[2].id)
    assert res.status_code < 400
    assert o.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_transition_to_paid_expired_quota_full(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_EXPIRED
    o.save()
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'p'
    })
    o = Order.objects.get(id=env[2].id)
    assert o.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
@pytest.mark.parametrize("process", [
    # (Old status, new status, success expected)
    (Order.STATUS_CANCELLED, Order.STATUS_PAID, False),
    (Order.STATUS_CANCELLED, Order.STATUS_PENDING, False),
    (Order.STATUS_CANCELLED, Order.STATUS_REFUNDED, False),

    (Order.STATUS_PAID, Order.STATUS_PENDING, True),
    (Order.STATUS_PAID, Order.STATUS_CANCELLED, False),
    (Order.STATUS_PAID, Order.STATUS_REFUNDED, True),

    (Order.STATUS_PENDING, Order.STATUS_CANCELLED, True),
    (Order.STATUS_PENDING, Order.STATUS_PAID, True),
    (Order.STATUS_PENDING, Order.STATUS_REFUNDED, False),

    (Order.STATUS_REFUNDED, Order.STATUS_CANCELLED, False),
    (Order.STATUS_REFUNDED, Order.STATUS_PAID, False),
    (Order.STATUS_REFUNDED, Order.STATUS_PENDING, False)
])
def test_order_transition(client, env, process):
    o = Order.objects.get(id=env[2].id)
    o.status = process[0]
    o.save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': process[1]
    })
    o = Order.objects.get(id=env[2].id)
    if process[2]:
        assert o.status == process[1]
    else:
        assert o.status == process[0]


@pytest.mark.django_db
def test_order_detail_download_buttons_hidden_if_not_paid(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PENDING
    o.save()
    env[0].settings.set('ticket_download', True)
    del env[0].settings['ticket_download_date']
    env[0].settings.set('ticketoutput_testdummy__enabled', True)
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/')
    assert '/control/event/dummy/dummy/orders/FOO/download/testdummy' not in response.rendered_content


@pytest.mark.django_db
def test_order_detail_download_buttons_visible(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PAID
    o.save()
    env[0].settings.set('ticket_download', True)
    del env[0].settings['ticket_download_date']
    env[0].settings.set('ticketoutput_testdummy__enabled', True)
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/')
    assert '/control/event/dummy/dummy/orders/FOO/download/testdummy' in response.rendered_content


@pytest.mark.django_db
def test_order_detail_download_buttons_hidden_of(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PAID
    o.save()
    env[0].settings.set('ticket_download', False)
    del env[0].settings['ticket_download_date']
    env[0].settings.set('ticketoutput_testdummy__enabled', True)
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/')
    assert '/control/event/dummy/dummy/orders/FOO/download/testdummy' not in response.rendered_content


@pytest.mark.django_db
def test_order_detail_download_buttons_visible_before_date(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PAID
    o.save()
    env[0].settings.set('ticket_download', True)
    env[0].settings.set('ticketoutput_testdummy__enabled', True)
    env[0].settings['ticket_download_date'] = now() + timedelta(days=30)
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/')
    assert '/control/event/dummy/dummy/orders/FOO/download/testdummy' in response.rendered_content


@pytest.mark.django_db
def test_order_detail_download_buttons_hidden_if_provider_disabled(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PAID
    o.save()
    env[0].settings.set('ticket_download', True)
    del env[0].settings['ticket_download_date']
    env[0].settings.set('ticketoutput_testdummy__enabled', False)
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/')
    assert '/control/event/dummy/dummy/orders/FOO/download/testdummy' not in response.rendered_content


@pytest.mark.django_db
def test_order_download_unpaid(client, env):
    env[0].settings.set('ticket_download', True)
    del env[0].settings['ticket_download_date']
    env[0].settings.set('ticketoutput_testdummy__enabled', True)
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/download/testdummy', follow=True)
    assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_order_download_unknown_provider(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PAID
    o.save()
    env[0].settings.set('ticket_download', True)
    del env[0].settings['ticket_download_date']
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/download/foobar', follow=True)
    assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_order_download_disabled_provider(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PAID
    o.save()
    env[0].settings.set('ticket_download', True)
    del env[0].settings['ticket_download_date']
    env[0].settings.set('ticketoutput_testdummy__enabled', False)
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/download/testdummy', follow=True)
    assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_order_download_success(client, env, mocker):
    from pretix.base.services import tickets
    mocker.patch('pretix.base.services.tickets.generate')
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PAID
    o.save()
    env[0].settings.set('ticket_download', True)
    del env[0].settings['ticket_download_date']
    env[0].settings.set('ticketoutput_testdummy__enabled', True)
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/download/testdummy')
    assert response.status_code == 302
    tickets.generate.assert_any_call(o.id, 'testdummy')
    assert 'download' in response['Location']
    dl = response['Location']
    assert CachedTicket.objects.filter(order=o, provider='testdummy').exists()

    # test caching
    tickets.generate.reset_mock()
    response = client.get('/control/event/dummy/dummy/orders/FOO/download/testdummy')
    assert response.status_code == 302
    assert tickets.generate.assert_not_called()
    assert dl == response['Location']


@pytest.mark.django_db
def test_order_extend_not_pending(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PAID
    o.save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/extend', follow=True)
    assert 'alert-danger' in response.rendered_content
    response = client.post('/control/event/dummy/dummy/orders/FOO/extend', follow=True)
    assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_order_extend_not_expired(client, env):
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    newdate = (now() + timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/extend', {
        'expires': newdate
    }, follow=True)
    assert 'alert-success' in response.rendered_content
    o = Order.objects.get(id=env[2].id)
    assert o.expires.strftime("%Y-%m-%d %H:%M:%S") == newdate


@pytest.mark.django_db
def test_order_extend_expired_quota_left(client, env):
    o = Order.objects.get(id=env[2].id)
    o.expires = now() - timedelta(days=5)
    o.save()
    q = Quota.objects.create(event=env[0], size=3)
    q.items.add(env[3])
    newdate = (now() + timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/extend', {
        'expires': newdate
    }, follow=True)
    assert 'alert-success' in response.rendered_content
    o = Order.objects.get(id=env[2].id)
    assert o.expires.strftime("%Y-%m-%d %H:%M:%S") == newdate


@pytest.mark.django_db
def test_order_extend_expired_quota_empty(client, env):
    o = Order.objects.get(id=env[2].id)
    o.expires = now() - timedelta(days=5)
    olddate = o.expires
    o.save()
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    newdate = (now() + timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/extend', {
        'expires': newdate
    }, follow=True)
    assert 'alert-danger' in response.rendered_content
    o = Order.objects.get(id=env[2].id)
    assert o.expires.strftime("%Y-%m-%d %H:%M:%S") == olddate.strftime("%Y-%m-%d %H:%M:%S")


@pytest.mark.django_db
def test_order_go_lowercase(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/go?code=DuMmyfoO')
    assert response['Location'].endswith('/control/event/dummy/dummy/orders/FOO/')


@pytest.mark.django_db
def test_order_go_with_slug(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/go?code=DUMMYFOO')
    assert response['Location'].endswith('/control/event/dummy/dummy/orders/FOO/')


@pytest.mark.django_db
def test_order_go_found(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/go?code=FOO')
    assert response['Location'].endswith('/control/event/dummy/dummy/orders/FOO/')


@pytest.mark.django_db
def test_order_go_not_found(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/go?code=BAR')
    assert response['Location'].endswith('/control/event/dummy/dummy/orders/')
