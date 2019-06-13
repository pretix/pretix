from datetime import timedelta

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, Item, Organizer, Quota, Team, User, Voucher, WaitingListEntry,
)
from pretix.control.views.dashboards import waitinglist_widgets


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,tests.testdummy'
    )
    event.settings.set('ticketoutput_testdummy__enabled', True)
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    item1 = Item.objects.create(event=event, name="Ticket", default_price=23,
                                admission=True)
    item2 = Item.objects.create(event=event, name="Ticket", default_price=23,
                                admission=True)

    for i in range(5):
        WaitingListEntry.objects.create(
            event=event, item=item1, email='foo{}@bar.com'.format(i)
        )
    v = Voucher.objects.create(item=item1, event=event, block_quota=True, redeemed=1)
    WaitingListEntry.objects.create(
        event=event, item=item1, email='success@example.org', voucher=v
    )
    v = Voucher.objects.create(item=item1, event=event, block_quota=True, redeemed=0, valid_until=now() - timedelta(days=5))
    WaitingListEntry.objects.create(
        event=event, item=item2, email='expired@example.org', voucher=v
    )
    v = Voucher.objects.create(item=item1, event=event, block_quota=True, redeemed=0, valid_until=now() + timedelta(days=5))
    WaitingListEntry.objects.create(
        event=event, item=item2, email='valid@example.org', voucher=v
    )

    t = Team.objects.create(organizer=o, can_view_orders=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)
    return event, user, o, item1


@pytest.mark.django_db
def test_list(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')

    response = client.get('/control/event/dummy/dummy/waitinglist/')
    assert 'success@example.org' not in response.content.decode()
    assert 'expired@example.org' not in response.content.decode()
    assert 'foo0@bar.com' in response.content.decode()
    assert 'valid@example.org' not in response.content.decode()
    assert response.context['estimate'] == 23 * 5

    response = client.get('/control/event/dummy/dummy/waitinglist/?status=a')
    assert 'success@example.org' in response.content.decode()
    assert 'foo0@bar.com' in response.content.decode()
    assert 'expired@example.org' in response.content.decode()
    assert 'valid@example.org' in response.content.decode()

    response = client.get('/control/event/dummy/dummy/waitinglist/?status=s')
    assert 'success@example.org' in response.content.decode()
    assert 'foo0@bar.com' not in response.content.decode()
    assert 'expired@example.org' in response.content.decode()
    assert 'valid@example.org' in response.content.decode()

    response = client.get('/control/event/dummy/dummy/waitinglist/?status=v')
    assert 'success@example.org' not in response.content.decode()
    assert 'foo0@bar.com' not in response.content.decode()
    assert 'expired@example.org' not in response.content.decode()
    assert 'valid@example.org' in response.content.decode()

    response = client.get('/control/event/dummy/dummy/waitinglist/?status=r')
    assert 'success@example.org' in response.content.decode()
    assert 'foo0@bar.com' not in response.content.decode()
    assert 'expired@example.org' not in response.content.decode()
    assert 'valid@example.org' not in response.content.decode()

    response = client.get('/control/event/dummy/dummy/waitinglist/?status=e')
    assert 'success@example.org' not in response.content.decode()
    assert 'expired@example.org' in response.content.decode()
    assert 'foo0@bar.com' not in response.content.decode()
    assert 'valid@example.org' not in response.content.decode()

    response = client.get('/control/event/dummy/dummy/waitinglist/?item=%d' % env[3].pk)
    assert 'item2@example.org' not in response.content.decode()
    assert 'foo0@bar.com' in response.content.decode()


@pytest.mark.django_db
def test_assign_single(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        wle = WaitingListEntry.objects.filter(voucher__isnull=True).last()

    client.post('/control/event/dummy/dummy/waitinglist/', {
        'assign': wle.pk
    })
    wle.refresh_from_db()
    assert wle.voucher


@pytest.mark.django_db
def test_priority_single(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        wle = WaitingListEntry.objects.filter(voucher__isnull=True).last()
    assert wle.priority == 0

    client.post('/control/event/dummy/dummy/waitinglist/', {
        'move_top': wle.pk
    })
    wle.refresh_from_db()
    assert wle.priority == 1
    client.post('/control/event/dummy/dummy/waitinglist/', {
        'move_top': wle.pk
    })
    wle.refresh_from_db()
    assert wle.priority == 2
    client.post('/control/event/dummy/dummy/waitinglist/', {
        'move_end': wle.pk
    })
    wle.refresh_from_db()
    assert wle.priority == -1


@pytest.mark.django_db
def test_delete_single(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        wle = WaitingListEntry.objects.first()

    client.post('/control/event/dummy/dummy/waitinglist/%s/delete' % (wle.id))
    with pytest.raises(WaitingListEntry.DoesNotExist):
        with scopes_disabled():
            WaitingListEntry.objects.get(id=wle.id)


@pytest.mark.django_db
def test_dashboard(client, env):
    with scopes_disabled():
        quota = Quota.objects.create(name="Test", size=2, event=env[0])
        quota.items.add(env[3])
        w = waitinglist_widgets(env[0])
    assert '1' in w[0]['content']
    assert '5' in w[1]['content']
