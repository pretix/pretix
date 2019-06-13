import json
from datetime import timedelta

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Checkin, Event, Item, ItemVariation, Order, OrderPosition, Organizer, Team,
    User,
)
from pretix.plugins.pretixdroid.models import AppConfiguration
from pretix.plugins.pretixdroid.views import API_VERSION


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.pretixdroid',
        has_subevents=True
    )
    se1 = event.subevents.create(name='Foo', date_from=now())
    se2 = event.subevents.create(name='Bar', date_from=now())
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
        total=0
    )
    op1 = OrderPosition.objects.create(
        order=o1, item=shirt, variation=shirt_red,
        price=12, attendee_name_parts={}, secret='1234', subevent=se1
    )
    op2 = OrderPosition.objects.create(
        order=o1, item=ticket,
        price=23, attendee_name_parts={'full_name': "Peter"}, secret='5678910', subevent=se2
    )
    cl1 = event.checkin_lists.create(name="Foo", all_products=True, subevent=se1)
    cl2 = event.checkin_lists.create(name="Foo", all_products=True, subevent=se2)
    return event, user, o1, op1, op2, se1, se2, cl1, cl2


@pytest.mark.django_db
def test_custom_datetime(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[7])
    dt = now() - timedelta(days=1)
    dt = dt.replace(microsecond=0)
    resp = client.post('/pretixdroid/api/%s/%s/%d/redeem/?key=%s' % (
        env[0].organizer.slug, env[0].slug, env[5].pk, 'abcdefg'
    ), data={'secret': '1234', 'datetime': dt.isoformat()})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['version'] == API_VERSION
    assert jdata['status'] == 'ok'
    with scopes_disabled():
        assert Checkin.objects.last().datetime == dt


@pytest.mark.django_db
def test_wrong_subevent(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[8])

    resp = client.post('/pretixdroid/api/%s/%s/%d/redeem/?key=%s' % (
        env[0].organizer.slug, env[0].slug, env[5].pk, 'abcdefg'
    ), data={'secret': '5678910'})
    assert resp.status_code == 403

    resp = client.post('/pretixdroid/api/%s/%s/%d/redeem/?key=%s' % (
        env[0].organizer.slug, env[0].slug, env[6].pk, 'abcdefg'
    ), data={'secret': '5678910'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['status'] == 'ok'


@pytest.mark.django_db
def test_other_subevent_not_allowed(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[7])
    resp = client.post('/pretixdroid/api/%s/%s/%d/redeem/?key=%s' % (
        env[0].organizer.slug, env[0].slug, env[6].pk, 'abcdefg'
    ), data={'secret': '5678910'})
    assert resp.status_code == 403

    env[7].subevent = env[6]
    env[7].save()

    resp = client.post('/pretixdroid/api/%s/%s/%d/redeem/?key=%s' % (
        env[0].organizer.slug, env[0].slug, env[6].pk, 'abcdefg'
    ), data={'secret': '5678910'})
    jdata = json.loads(resp.content.decode("utf-8"))
    assert jdata['status'] == 'ok'


@pytest.mark.django_db
def test_unknown_subevent(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[7])
    resp = client.post('/pretixdroid/api/%s/%s/%d/redeem/?key=%s' % (
        env[0].organizer.slug, env[0].slug, env[6].pk + 1000, 'abcdefg'
    ), data={'secret': '5678910'})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_no_subevent(client, env):
    resp = client.post('/pretixdroid/api/%s/%s/redeem/?key=%s' % (
        env[0].organizer.slug, env[0].slug, 'abcdefg'
    ), data={'secret': '5678910'})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_search(client, env):
    AppConfiguration.objects.create(event=env[0], key='hijklmn', list=env[7])
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[8])
    resp = client.get('/pretixdroid/api/%s/%s/%d/search/?key=%s&query=%s' % (
        env[0].organizer.slug, env[0].slug, env[5].pk, 'hijklmn', '567891'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 0
    resp = client.get('/pretixdroid/api/%s/%s/%d/search/?key=%s&query=%s' % (
        env[0].organizer.slug, env[0].slug, env[6].pk, 'abcdefg', '567891'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 1
    assert jdata['results'][0]['secret'] == '5678910'


@pytest.mark.django_db
def test_download_all_data(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[7])
    resp = client.get('/pretixdroid/api/%s/%s/%d/download/?key=%s' % (
        env[0].organizer.slug, env[0].slug, env[5].pk, 'abcdefg'))
    jdata = json.loads(resp.content.decode("utf-8"))
    assert len(jdata['results']) == 1
    assert jdata['results'][0]['secret'] == '1234'


@pytest.mark.django_db
def test_status(client, env):
    AppConfiguration.objects.create(event=env[0], key='abcdefg', list=env[7])
    with scopes_disabled():
        Checkin.objects.create(position=env[3], list=env[7])
    resp = client.get('/pretixdroid/api/%s/%s/%d/status/?key=%s' % (
        env[0].organizer.slug, env[0].slug, env[5].pk, 'abcdefg'))
    jdata = json.loads(resp.content.decode("utf-8"))
    with scopes_disabled():
        assert jdata['checkins'] == 1
        assert jdata['total'] == 1
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
             'total': 0,
             'variations': []
             }
        ]
