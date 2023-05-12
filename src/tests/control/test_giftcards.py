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

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Order, OrderPayment, OrderRefund, Organizer, Team, User,
)


@pytest.fixture
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
def organizer2():
    return Organizer.objects.create(name='Partner', slug='partner')


@pytest.fixture
def gift_card(organizer):
    gc = organizer.issued_gift_cards.create(currency="EUR")
    gc.transactions.create(value=42, acceptor=organizer)
    return gc


@pytest.fixture
def admin_user(organizer):
    u = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    admin_team = Team.objects.create(organizer=organizer, can_manage_gift_cards=True, name='Admin team',
                                     can_change_organizer_settings=True)
    admin_team.members.add(u)
    return u


@pytest.fixture
def team2(admin_user, organizer2):
    admin_team = Team.objects.create(organizer=organizer2, can_manage_gift_cards=True, name='Admin team')
    admin_team.members.add(admin_user)


@pytest.mark.django_db
def test_list_of_cards(organizer, admin_user, client, gift_card):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/giftcards')
    assert gift_card.secret in resp.content.decode()
    resp = client.get('/control/organizer/dummy/giftcards?query=' + gift_card.secret[:3])
    assert gift_card.secret in resp.content.decode()
    resp = client.get('/control/organizer/dummy/giftcards?query=1234_FOO')
    assert gift_card.secret not in resp.content.decode()


@pytest.mark.django_db
def test_card_detail_view(organizer, admin_user, gift_card, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/giftcard/{}/'.format(gift_card.pk))
    assert gift_card.secret in resp.content.decode()
    assert '42.00' in resp.content.decode()


@pytest.mark.django_db
def test_card_add(organizer, admin_user, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.post('/control/organizer/dummy/giftcard/add', {
        'currency': 'EUR',
        'secret': 'FOOBAR',
        'value': '42.00',
        'testmode': 'on'
    }, follow=True)
    assert 'TEST MODE' in resp.content.decode()
    assert '42.00' in resp.content.decode()
    resp = client.post('/control/organizer/dummy/giftcard/add', {
        'currency': 'EUR',
        'secret': 'FOOBAR',
        'value': '42.00',
        'testmode': 'on'
    }, follow=True)
    assert 'has-error' in resp.content.decode()


@pytest.mark.django_db
def test_card_detail_view_transact(organizer, admin_user, gift_card, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/giftcard/{}/'.format(gift_card.pk), {
        'value': '23.00'
    })
    assert gift_card.value == 23 + 42
    assert gift_card.all_logentries().count() == 1


@pytest.mark.django_db
def test_card_detail_edit(organizer, admin_user, gift_card, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/giftcard/{}/edit'.format(gift_card.pk), {
        'conditions': 'Foo'
    })
    gift_card.refresh_from_db()
    assert gift_card.conditions == 'Foo'


@pytest.mark.django_db
def test_card_detail_view_transact_revert_refund(organizer, admin_user, gift_card, client):
    with scopes_disabled():
        event = organizer.events.create(
            name='Dummy', slug='dummy',
            date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.stripe,tests.testdummy'
        )
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_CANCELED,
            datetime=now(), expires=now() + timedelta(days=10),
            total=14, locale='en'
        )
        o.payments.create(
            amount=o.total, provider='banktransfer', state=OrderPayment.PAYMENT_STATE_CONFIRMED
        )
        r = o.refunds.create(
            amount=o.total, provider='giftcard', state=OrderRefund.REFUND_STATE_DONE
        )
        t = gift_card.transactions.create(value=14, order=o, refund=r, acceptor=organizer)

    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post('/control/organizer/dummy/giftcard/{}/'.format(gift_card.pk), {
        'revert': str(t.pk)
    })
    assert 'alert-success' in r.rendered_content
    assert gift_card.value == 42
    o.refresh_from_db()
    assert o.pending_sum == -14


@pytest.mark.django_db
def test_card_detail_view_transact_min_value(organizer, admin_user, gift_card, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post('/control/organizer/dummy/giftcard/{}/'.format(gift_card.pk), {
        'value': '-50.00'
    })
    assert 'alert-danger' in r.rendered_content
    assert gift_card.value == 42


@pytest.mark.django_db
def test_card_detail_view_transact_invalid_value(organizer, admin_user, gift_card, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post('/control/organizer/dummy/giftcard/{}/'.format(gift_card.pk), {
        'value': 'foo'
    })
    assert 'alert-danger' in r.rendered_content
    assert gift_card.value == 42


@pytest.mark.django_db
def test_manage_acceptance(organizer, organizer2, admin_user, gift_card, client, team2):
    gca = organizer.gift_card_issuer_acceptance.create(issuer=organizer2, active=False)

    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/giftcards/acceptance', {
        'accept_issuer': organizer2.slug
    })

    gca.refresh_from_db()
    assert gca.active

    client.post('/control/organizer/dummy/giftcards/acceptance', {
        'delete_issuer': organizer2.slug
    })
    assert not organizer.gift_card_issuer_acceptance.filter(issuer=organizer2).exists()

    client.post('/control/organizer/dummy/giftcards/acceptance/invite', {
        'acceptor': organizer2.slug
    })
    assert organizer.gift_card_acceptor_acceptance.filter(acceptor=organizer2).exists()
    client.post('/control/organizer/dummy/giftcards/acceptance', {
        'delete_acceptor': organizer2.slug
    })
    assert not organizer.gift_card_acceptor_acceptance.filter(acceptor=organizer2).exists()


@pytest.mark.django_db
def test_typeahead(organizer, admin_user, client, gift_card):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        team = organizer.teams.get()

    # Privileged user can search
    r = client.get('/control/organizer/dummy/giftcards/select2?query=' + gift_card.secret[0:3])
    d = json.loads(r.content)
    assert d == {"results": [{"id": gift_card.pk, "text": gift_card.secret}], "pagination": {"more": False}}

    # Unprivileged user can only do exact match
    team.can_manage_gift_cards = False
    team.can_manage_reusable_media = True
    team.save()

    r = client.get('/control/organizer/dummy/giftcards/select2?query=' + gift_card.secret[0:3])
    d = json.loads(r.content)
    assert d == {"results": [], "pagination": {"more": False}}
    r = client.get('/control/organizer/dummy/giftcards/select2?query=' + gift_card.secret)
    d = json.loads(r.content)
    assert d == {"results": [{"id": gift_card.pk, "text": gift_card.secret}], "pagination": {"more": False}}
