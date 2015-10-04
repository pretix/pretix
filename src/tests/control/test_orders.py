from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now

from pretix.base.models import (
    Event, EventPermission, Item, Order, OrderPosition, Organizer,
    OrganizerPermission, User,
)


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
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
    return event, user, o


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


@pytest.mark.django_db
def test_order_detail(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/')
    assert 'Early-bird' in response.rendered_content
    assert 'Peter' in response.rendered_content


@pytest.mark.django_db
def test_order_transition_cancel(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'c'
    })
    o = Order.objects.current.get(identity=env[2].identity)
    assert o.status == Order.STATUS_CANCELLED


@pytest.mark.django_db
def test_order_transition_to_paid_success(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'p'
    })
    o = Order.objects.current.get(identity=env[2].identity)
    assert o.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_transition_to_unpaid_success(client, env):
    o = Order.objects.current.get(identity=env[2].identity)
    o.status = Order.STATUS_PAID
    o.save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'n'
    })
    o = Order.objects.current.get(identity=env[2].identity)
    assert o.status == Order.STATUS_PENDING
