import copy
import json

import pytest
from django.utils.timezone import now

from pretix.base.models import Event, Item, Organizer, Team, User
from pretix.plugins.ticketoutputpdf.models import TicketLayoutItem


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    t = Team.objects.create(organizer=event.organizer)
    t.members.add(user)
    t.limit_events.add(event)
    item1 = Item.objects.create(event=event, name="Ticket", default_price=23)
    tl = event.ticket_layouts.create(name="Foo", default=True, layout='[{"a": 2}]')
    TicketLayoutItem.objects.create(layout=tl, item=item1)
    return event, user, tl, item1


RES_LAYOUT = {
    'id': 1,
    'name': 'Foo',
    'default': True,
    'item_assignments': [{'item': 1, 'sales_channel': 'web'}],
    'layout': [{'a': 2}],
    'background': None
}


@pytest.mark.django_db
def test_api_list(env, client):
    res = copy.copy(RES_LAYOUT)
    res['id'] = env[2].pk
    res['item_assignments'][0]['item'] = env[3].pk
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(
        client.get('/api/v1/organizers/{}/events/{}/ticketlayouts/'.format(
            env[0].slug, env[0].organizer.slug)).content.decode('utf-8')
    )
    assert r['results'] == [res]
    r = json.loads(
        client.get('/api/v1/organizers/{}/events/{}/ticketlayoutitems/'.format(
            env[0].slug, env[0].organizer.slug)).content.decode('utf-8')
    )
    assert r['results'] == [{'item': env[3].pk, 'layout': env[2].pk, 'id': env[2].item_assignments.first().pk,
                             'sales_channel': 'web'}]


@pytest.mark.django_db
def test_api_detail(env, client):
    res = copy.copy(RES_LAYOUT)
    res['id'] = env[2].pk
    res['item_assignments'][0]['item'] = env[3].pk
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(
        client.get('/api/v1/organizers/{}/events/{}/ticketlayouts/{}/'.format(
            env[0].slug, env[0].organizer.slug, env[2].pk)).content.decode('utf-8')
    )
    assert r == res
