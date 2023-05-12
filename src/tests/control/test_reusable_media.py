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
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Order, Organizer, Team, User


@pytest.fixture
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
def medium(organizer):
    m = organizer.reusable_media.create(identifier="ABCDEFGH", type="barcode")
    return m


@pytest.fixture
def gift_card(organizer):
    gc = organizer.issued_gift_cards.create(currency="EUR")
    gc.transactions.create(value=42, acceptor=organizer)
    return gc


@pytest.fixture
def admin_user(organizer):
    u = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    admin_team = Team.objects.create(organizer=organizer, can_manage_reusable_media=True, name='Admin team')
    admin_team.members.add(u)
    return u


@pytest.mark.django_db
def test_list_of_media(organizer, admin_user, client, medium):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/reusable_media')
    assert medium.identifier in resp.content.decode()
    resp = client.get('/control/organizer/dummy/reusable_media?query=' + medium.identifier[:3])
    assert medium.identifier in resp.content.decode()
    resp = client.get('/control/organizer/dummy/reusable_media?query=1234_FOO')
    assert medium.identifier not in resp.content.decode()


@pytest.mark.django_db
def test_medium_detail_view(organizer, admin_user, medium, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/reusable_media/{}/'.format(medium.pk))
    assert medium.identifier in resp.content.decode()


@pytest.mark.django_db
def test_medium_add(organizer, admin_user, client, gift_card):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.post('/control/organizer/dummy/reusable_media/add', {
        'type': 'barcode',
        'identifier': 'FOOBAR',
        'linked_giftcard': gift_card.pk,
    }, follow=True)
    assert 'FOOBAR' in resp.content.decode()
    assert gift_card.secret in resp.content.decode()
    with scopes_disabled():
        m = organizer.reusable_media.get()
    assert m.linked_giftcard == gift_card
    assert m.type == 'barcode'
    assert m.identifier == 'FOOBAR'


@pytest.mark.django_db
def test_medium_update(organizer, admin_user, client, medium, gift_card):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post(f'/control/organizer/dummy/reusable_media/{medium.pk}/edit', {
        'active': 'on',
        'linked_giftcard': gift_card.pk,
    }, follow=True)
    medium.refresh_from_db()
    assert medium.linked_giftcard == gift_card


@pytest.mark.django_db
def test_typeahead(organizer, admin_user, client, gift_card):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        event = organizer.events.create(
            name='Dummy', slug='dummy', date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.stripe,tests.testdummy'
        )
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, datetime=now(), expires=now() + timedelta(days=10),
            total=14, locale='en'
        )
        ticket = event.items.create(name='Early-bird ticket', category=None, default_price=23, admission=True, personalized=True)
        op = o.positions.create(item=ticket, price=Decimal("14"))

        team = organizer.teams.get()

    # Privileged user can search
    team.all_events = True
    team.can_view_orders = True
    team.save()

    r = client.get('/control/organizer/dummy/ticket_select2?query=' + op.secret[0:3])
    d = json.loads(r.content)
    assert d == {"results": [{'event': 'Dummy', 'id': op.pk, 'text': 'FOO-1 (Early-bird ticket)'}], "pagination": {"more": False}}
    r = client.get('/control/organizer/dummy/ticket_select2?query=DUMMY-FOO-1')
    d = json.loads(r.content)
    assert d == {"results": [{'event': 'Dummy', 'id': op.pk, 'text': 'FOO-1 (Early-bird ticket)'}], "pagination": {"more": False}}
    r = client.get('/control/organizer/dummy/ticket_select2?query=DUMMY-FOO')
    d = json.loads(r.content)
    assert d == {"results": [{'event': 'Dummy', 'id': op.pk, 'text': 'FOO-1 (Early-bird ticket)'}], "pagination": {"more": False}}
    r = client.get('/control/organizer/dummy/ticket_select2?query=FOO-1')
    d = json.loads(r.content)
    assert d == {"results": [{'event': 'Dummy', 'id': op.pk, 'text': 'FOO-1 (Early-bird ticket)'}], "pagination": {"more": False}}

    # Unprivileged user can only do exact match
    team.all_events = True
    team.can_view_orders = False
    team.save()

    r = client.get('/control/organizer/dummy/ticket_select2?query=' + op.secret[0:3])
    d = json.loads(r.content)
    assert d == {"results": [], "pagination": {"more": False}}
    r = client.get('/control/organizer/dummy/ticket_select2?query=FOO-1')
    d = json.loads(r.content)
    assert d == {"results": [], "pagination": {"more": False}}
    r = client.get('/control/organizer/dummy/ticket_select2?query=' + op.secret)
    d = json.loads(r.content)
    assert d == {"results": [{'event': 'Dummy', 'id': op.pk, 'text': 'FOO-1 (Early-bird ticket)'}], "pagination": {"more": False}}

    team.all_events = False
    team.can_view_orders = True
    team.save()

    r = client.get('/control/organizer/dummy/ticket_select2?query=' + op.secret[0:3])
    d = json.loads(r.content)
    assert d == {"results": [], "pagination": {"more": False}}
    r = client.get('/control/organizer/dummy/ticket_select2?query=FOO-1')
    d = json.loads(r.content)
    assert d == {"results": [], "pagination": {"more": False}}
    r = client.get('/control/organizer/dummy/ticket_select2?query=' + op.secret)
    d = json.loads(r.content)
    assert d == {"results": [{'event': 'Dummy', 'id': op.pk, 'text': 'FOO-1 (Early-bird ticket)'}], "pagination": {"more": False}}
