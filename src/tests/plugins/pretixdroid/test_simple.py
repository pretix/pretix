import json
from datetime import timedelta

import pytest
from django.utils.timezone import now

from pretix.base.models import (
    Checkin, Event, InvoiceAddress, Item, ItemVariation, Order, OrderPosition,
    Organizer, Team, User,
)
from pretix.plugins.pretixdroid.models import AppConfiguration
from pretix.plugins.pretixdroid.views import API_VERSION


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.pretixdroid'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')

    t = Team.objects.create(organizer=o, can_change_event_settings=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)

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
        price=23, attendee_name="Peter", secret='5678910'
    )
    cl1 = event.checkin_lists.create(name="Foo", all_products=True)
    cl2 = event.checkin_lists.create(name="Bar", all_products=True)
    return event, user, o1, op1, op2, cl1, cl2


@pytest.mark.django_db
def test_custom_datetime(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5])
    dt = now() - timedelta(days=1)
    dt = dt.replace(microsecond=0)
    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234', 'datetime': dt.isoformat()})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['version'] == API_VERSION
    assert jdata['status'] == 'ok'
    assert Checkin.objects.last().datetime == dt


@pytest.mark.django_db
def test_only_once(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5])

    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['version'] == API_VERSION
    assert jdata['status'] == 'ok'
    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['status'] == 'error'
    assert jdata['reason'] == 'already_redeemed'


@pytest.mark.django_db
def test_item_scope(client, env):
    ac = AppConfiguration.objects.create(event=env[0], key='abcdefg', all_items=False, list=env[5])
    ac.items.add(env[4].item)

    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': env[4].secret})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['version'] == API_VERSION
    assert jdata['status'] == 'ok'
    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': env[3].secret})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['status'] == 'error'
    assert jdata['reason'] == 'product'


@pytest.mark.django_db
def test_item_restricted_list(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', all_items=True, list=env[5])
    env[5].all_products = False
    env[5].limit_products.add(env[4].item)
    env[5].save()

    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': env[4].secret})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['version'] == API_VERSION
    assert jdata['status'] == 'ok'
    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': env[3].secret})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['status'] == 'error'
    assert jdata['reason'] == 'product'


@pytest.mark.django_db
def test_reupload_same_nonce(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5])

    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234', 'nonce': 'fooobar'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['version'] == API_VERSION
    assert jdata['status'] == 'ok'
    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234', 'nonce': 'fooobar'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['status'] == 'ok'
    assert Checkin.objects.count() == 1


@pytest.mark.django_db
def test_multiple_different_list(client, env):
    ac = AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5])

    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['version'] == API_VERSION
    assert jdata['status'] == 'ok'

    ac.list = env[6]
    ac.save()
    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['status'] == 'ok'


@pytest.mark.django_db
def test_forced_multiple(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5])

    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['version'] == API_VERSION
    assert jdata['status'] == 'ok'
    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234', 'force': 'true'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['status'] == 'ok'


@pytest.mark.django_db
def test_require_paid(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5])
    env[2].status = Order.STATUS_PENDING
    env[2].save()

    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'),
                       data={'secret': '1234'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['status'] == 'error'
    assert jdata['reason'] == 'unpaid'


@pytest.mark.django_db
def test_unknown(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5])

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


@pytest.mark.django_db
def test_search(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5])
    resp = client.get('/pretixdroid/api/%s/%s/search/?key=%s&query=%s' % (
        env[0].organizer.slug, env[0].slug, 'abcdefg', '567891'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 1
    assert jdata['results'][0]['secret'] == '5678910'
    resp = client.get('/pretixdroid/api/%s/%s/search/?key=%s&query=%s' % (
        env[0].organizer.slug, env[0].slug, 'abcdefg', 'Peter'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 1
    assert jdata['results'][0]['secret'] == '5678910'


@pytest.mark.django_db
def test_search_item_restricted_list(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5])
    env[5].all_products = False
    env[5].limit_products.add(env[4].item)
    env[5].save()

    resp = client.get('/pretixdroid/api/%s/%s/search/?key=%s&query=%s' % (
        env[0].organizer.slug, env[0].slug, 'abcdefg', '567891'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 1
    assert jdata['results'][0]['secret'] == env[4].secret
    env[5].limit_products.remove(env[4].item)
    resp = client.get('/pretixdroid/api/%s/%s/search/?key=%s&query=%s' % (
        env[0].organizer.slug, env[0].slug, 'abcdefg', '567891'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 0


@pytest.mark.django_db
def test_search_restricted(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5], allow_search=False)
    resp = client.get('/pretixdroid/api/%s/%s/search/?key=%s&query=%s' % (
        env[0].organizer.slug, env[0].slug, 'abcdefg', '567891'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 1
    assert jdata['results'][0]['secret'] == '5678910'
    resp = client.get('/pretixdroid/api/%s/%s/search/?key=%s&query=%s' % (
        env[0].organizer.slug, env[0].slug, 'abcdefg', 'Peter'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 0


@pytest.mark.django_db
def test_search_invoice_name(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5])
    InvoiceAddress.objects.create(order=env[2], name="John")
    resp = client.get('/pretixdroid/api/%s/%s/search/?key=%s&query=%s' % (
        env[0].organizer.slug, env[0].slug, 'abcdefg', 'John'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 2
    assert set([r['attendee_name'] for r in jdata['results']]) == {'John', 'Peter'}


@pytest.mark.django_db
def test_download_all_data(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5])
    resp = client.get('/pretixdroid/api/%s/%s/download/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 2
    assert jdata['results'][0]['secret'] == '1234'
    assert jdata['results'][1]['secret'] == '5678910'


@pytest.mark.django_db
def test_download_item_restriction(client, env):
    ac = AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5], all_items=False)
    ac.items.add(env[4].item)
    resp = client.get('/pretixdroid/api/%s/%s/download/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 1
    assert jdata['results'][0]['secret'] == env[4].secret


@pytest.mark.django_db
def test_download_item_restricted_list(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', all_items=True, list=env[5])
    env[5].all_products = False
    env[5].limit_products.add(env[4].item)
    env[5].save()
    resp = client.get('/pretixdroid/api/%s/%s/download/?key=%s' % (env[0].organizer.slug, env[0].slug, 'abcdefg'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 1
    assert jdata['results'][0]['secret'] == env[4].secret


@pytest.mark.django_db
def test_status(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[5])
    Checkin.objects.create(position=env[3], list=env[5])
    resp = client.get('/pretixdroid/api/%s/%s/status/?key=%s' % (
        env[0].organizer.slug, env[0].slug, 'abcdefg'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['checkins'] == 1
    assert jdata['total'] == 2
    assert jdata['items'] == [
        {'name': 'T-Shirt',
         'id': env[3].item.pk,
         'checkins': 1,
         'admission': False,
         'total': 1,
         'variations': [
             {'name': 'Red',
              'id': env[3].variation.pk,
              'checkins': 1,
              'total': 1
              },
             {'name': 'Blue',
              'id': env[3].item.variations.get(value='Blue').pk,
              'checkins': 0,
              'total': 0
              }
         ]
         },
        {'name': 'Ticket',
         'id': env[4].item.pk,
         'checkins': 0,
         'admission': False,
         'total': 1,
         'variations': []
         }
    ]
