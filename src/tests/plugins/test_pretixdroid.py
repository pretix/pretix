import json
from datetime import timedelta

import pytest
from django.utils.timezone import now

from pretix.base.models import (
    Event, EventPermission, Item, ItemVariation, Order, OrderPosition,
    Organizer, User,
)


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.pretixdroid'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    EventPermission.objects.create(user=user, event=event)
    shirt = Item.objects.create(event=event, name='T-Shirt', default_price=12)
    shirt_red = ItemVariation.objects.create(item=shirt, default_price=14, value="Red")
    ItemVariation.objects.create(item=shirt, value="Blue")
    ticket = Item.objects.create(event=event, name='Ticket', default_price=23)
    o1 = Order.objects.create(
        code='FOO', event=event, status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0, payment_provider='banktransfer'
    )
    op1 = OrderPosition.objects.create(
        order=o1, item=shirt, variation=shirt_red,
        price=12, attendee_name=None, secret='1234'
    )
    op2 = OrderPosition.objects.create(
        order=o1, item=ticket,
        price=23, attendee_name="Peter", secret='5678'
    )
    return event, user, o1, op1, op2


@pytest.mark.django_db
def test_flush_key(client, env):
    env[0].settings.set('pretixdroid_key', 'abcdefg')

    client.get('/control/event/%s/%s/pretixdroid/' % (env[0].organizer.slug, env[0].slug))
    env[0].settings._flush()
    env[0].settings.get('pretixdroid_key') == 'abcdefg'

    client.get('/control/event/%s/%s/pretixdroid/?flush_key=1' % (env[0].organizer.slug, env[0].slug))
    env[0].settings._flush()
    env[0].settings.get('pretixdroid_key') != 'abcdefg'


@pytest.mark.django_db
def test_only_once(client, env):
    env[0].settings.set('pretixdroid_key', 'abcdefg')

    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['version'] == 2
    assert jdata['status'] == 'ok'
    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['status'] == 'error'
    assert jdata['reason'] == 'already_redeemed'


@pytest.mark.django_db
def test_require_paid(client, env):
    env[0].settings.set('pretixdroid_key', 'abcdefg')
    env[2].status = Order.STATUS_PENDING
    env[2].save()

    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['status'] == 'error'
    assert jdata['reason'] == 'unpaid'


@pytest.mark.django_db
def test_unknown(client, env):
    env[0].settings.set('pretixdroid_key', 'abcdefg')

    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '4321'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['status'] == 'error'
    assert jdata['reason'] == 'unknown_ticket'


@pytest.mark.django_db
def test_wrong_key(client, env):
    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, '12345'),
                       data={'secret': '4321'})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_unknown_event(client, env):
    resp = client.post('/pretixdroid/api/a/b/redeem/?key=c',
                       data={'secret': '4321'})
    assert resp.status_code == 404
