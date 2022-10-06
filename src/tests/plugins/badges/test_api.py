#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import copy
import json

import pytest
from django.utils.timezone import now

from pretix.base.models import Event, Item, Organizer, Team, User
from pretix.plugins.badges.models import BadgeItem


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
    tl = event.badge_layouts.create(name="Foo", default=True, layout='[{"a": 2}]')
    BadgeItem.objects.create(layout=tl, item=item1)
    return event, user, tl, item1


RES_LAYOUT = {
    'id': 1,
    'name': 'Foo',
    'default': True,
    'item_assignments': [{'item': 1}],
    'layout': [{'a': 2}],
    'background': 'http://example.com/static/pretixplugins/badges/badge_default_a6l.pdf'
}


@pytest.mark.django_db
def test_api_list(env, client):
    res = copy.copy(RES_LAYOUT)
    res['id'] = env[2].pk
    res['item_assignments'][0]['item'] = env[3].pk
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(
        client.get('/api/v1/organizers/{}/events/{}/badgelayouts/'.format(
            env[0].slug, env[0].organizer.slug)).content.decode('utf-8')
    )
    assert r['results'] == [res]
    r = json.loads(
        client.get('/api/v1/organizers/{}/events/{}/badgeitems/'.format(
            env[0].slug, env[0].organizer.slug)).content.decode('utf-8')
    )
    assert r['results'] == [{'item': env[3].pk, 'layout': env[2].pk, 'id': env[2].item_assignments.first().pk}]


@pytest.mark.django_db
def test_api_detail(env, client):
    res = copy.copy(RES_LAYOUT)
    res['id'] = env[2].pk
    res['item_assignments'][0]['item'] = env[3].pk
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(
        client.get('/api/v1/organizers/{}/events/{}/badgelayouts/{}/'.format(
            env[0].slug, env[0].organizer.slug, env[2].pk)).content.decode('utf-8')
    )
    assert r == res
