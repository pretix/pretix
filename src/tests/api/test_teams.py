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
import pytest
from django.core import mail
from django_scopes import scopes_disabled

from pretix.base.models import Team, User


@pytest.fixture
def second_team(organizer, event):
    t = organizer.teams.create(
        name='User team',
        all_events=False,
    )
    t.limit_events.add(event)
    return t


TEST_TEAM_RES = {
    'id': 1, 'name': 'Test-Team', 'all_events': True, 'limit_events': [], 'can_create_events': True,
    'can_change_teams': True, 'can_change_organizer_settings': True, 'can_manage_gift_cards': True,
    'can_manage_customers': True, 'can_manage_reusable_media': True,
    'can_change_event_settings': True, 'can_change_items': True, 'can_view_orders': True, 'can_change_orders': True,
    'can_view_vouchers': True, 'can_change_vouchers': True, 'can_checkin_orders': False
}

SECOND_TEAM_RES = {
    'id': 1, 'name': 'User team', 'all_events': False, 'limit_events': ['dummy'],
    'can_create_events': False,
    'can_manage_customers': False, 'can_manage_reusable_media': False,
    'can_change_teams': False, 'can_change_organizer_settings': False, 'can_manage_gift_cards': False,
    'can_change_event_settings': False, 'can_change_items': False, 'can_view_orders': False, 'can_change_orders': False,
    'can_view_vouchers': False, 'can_change_vouchers': False, 'can_checkin_orders': False
}


@pytest.mark.django_db
def test_team_list(token_client, organizer, event, team):
    res = dict(TEST_TEAM_RES)
    res["id"] = team.pk

    resp = token_client.get('/api/v1/organizers/{}/teams/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_team_detail(token_client, organizer, event, second_team):
    res = dict(SECOND_TEAM_RES)
    res["id"] = second_team.pk
    resp = token_client.get('/api/v1/organizers/{}/teams/{}/'.format(organizer.slug, second_team.pk))
    assert resp.status_code == 200
    assert res == resp.data


TEST_TEAM_CREATE_PAYLOAD = {
    "name": "Foobar",
    "limit_events": ["dummy"],
}


@pytest.mark.django_db
def test_team_create(token_client, organizer, event):
    resp = token_client.post(
        '/api/v1/organizers/{}/teams/'.format(organizer.slug),
        TEST_TEAM_CREATE_PAYLOAD,
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        team = Team.objects.get(pk=resp.data['id'])
        assert list(team.limit_events.all()) == [event]


@pytest.mark.django_db
def test_team_update(token_client, organizer, event, second_team):
    assert not second_team.can_change_event_settings
    resp = token_client.patch(
        '/api/v1/organizers/{}/teams/{}/'.format(organizer.slug, second_team.pk),
        {
            'can_change_event_settings': True,
        },
        format='json'
    )
    assert resp.status_code == 200
    second_team.refresh_from_db()
    assert second_team.can_change_event_settings

    resp = token_client.patch(
        '/api/v1/organizers/{}/teams/{}/'.format(organizer.slug, second_team.pk),
        {
            'all_events': True,
        },
        format='json'
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_team_delete(token_client, organizer, event, second_team):
    resp = token_client.delete(
        '/api/v1/organizers/{}/teams/{}/'.format(organizer.slug, second_team.pk),
        format='json'
    )
    assert resp.status_code == 204
    assert organizer.teams.count() == 1


TEST_TEAM_MEMBER_RES = {
    'email': 'dummy@dummy.dummy',
    'fullname': None,
    'require_2fa': False
}


@pytest.mark.django_db
def test_team_members_list(token_client, organizer, event, user, team):
    team.members.add(user)
    res = dict(TEST_TEAM_MEMBER_RES)
    res["id"] = user.pk

    resp = token_client.get('/api/v1/organizers/{}/teams/{}/members/'.format(organizer.slug, team.pk))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_team_members_detail(token_client, organizer, event, team, user):
    team.members.add(user)
    res = dict(TEST_TEAM_MEMBER_RES)
    res["id"] = user.pk
    resp = token_client.get('/api/v1/organizers/{}/teams/{}/members/{}/'.format(organizer.slug, team.pk, user.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_team_members_delete(token_client, organizer, event, team, user):
    team.members.add(user)
    resp = token_client.delete('/api/v1/organizers/{}/teams/{}/members/{}/'.format(organizer.slug, team.pk, user.pk))
    assert resp.status_code == 204
    assert team.members.count() == 0
    assert User.objects.filter(pk=user.pk).exists()


@pytest.fixture
def invite(team):
    return team.invites.create(email='foo@bar.com')


TEST_TEAM_INVITE_RES = {
    'email': 'foo@bar.com',
}


@pytest.mark.django_db
def test_team_invites_list(token_client, organizer, event, user, team, invite):
    res = dict(TEST_TEAM_INVITE_RES)
    res["id"] = invite.pk

    resp = token_client.get('/api/v1/organizers/{}/teams/{}/invites/'.format(organizer.slug, team.pk))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_team_invites_detail(token_client, organizer, event, team, user, invite):
    res = dict(TEST_TEAM_INVITE_RES)
    res["id"] = invite.pk
    resp = token_client.get('/api/v1/organizers/{}/teams/{}/invites/{}/'.format(organizer.slug, team.pk, invite.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_team_invites_delete(token_client, organizer, event, team, user, invite):
    resp = token_client.delete('/api/v1/organizers/{}/teams/{}/invites/{}/'.format(organizer.slug, team.pk, invite.pk))
    assert resp.status_code == 204
    assert team.invites.count() == 0


@pytest.mark.django_db
def test_team_invites_create(token_client, organizer, event, team, user):
    resp = token_client.post('/api/v1/organizers/{}/teams/{}/invites/'.format(organizer.slug, team.pk), {
        'email': 'newmail@dummy.dummy'
    })
    assert resp.status_code == 201
    assert team.invites.get().email == 'newmail@dummy.dummy'
    assert len(mail.outbox) == 1

    resp = token_client.post('/api/v1/organizers/{}/teams/{}/invites/'.format(organizer.slug, team.pk), {
        'email': 'newmail@dummy.dummy'
    })
    assert resp.status_code == 400
    assert resp.content.decode() == '["This user already has been invited for this team."]'

    resp = token_client.post('/api/v1/organizers/{}/teams/{}/invites/'.format(organizer.slug, team.pk), {
        'email': user.email
    })
    assert resp.status_code == 201
    assert not resp.data.get('id')
    assert team.invites.count() == 1
    assert user in team.members.all()

    resp = token_client.post('/api/v1/organizers/{}/teams/{}/invites/'.format(organizer.slug, team.pk), {
        'email': user.email
    })
    assert resp.status_code == 400
    assert resp.content.decode() == '["This user already has permissions for this team."]'


TEST_TEAM_TOKEN_RES = {
    'name': 'Testtoken',
    'active': True,
}


@pytest.fixture
def token(second_team):
    t = second_team.tokens.create(name='Testtoken')
    return t


@pytest.mark.django_db
def test_team_tokens_list(token_client, organizer, event, user, second_team, token):
    res = dict(TEST_TEAM_TOKEN_RES)
    res["id"] = token.pk

    resp = token_client.get('/api/v1/organizers/{}/teams/{}/tokens/'.format(organizer.slug, second_team.pk))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_team_tokens_detail(token_client, organizer, event, second_team, token):
    res = dict(TEST_TEAM_TOKEN_RES)
    res["id"] = token.pk
    resp = token_client.get(
        '/api/v1/organizers/{}/teams/{}/tokens/{}/'.format(organizer.slug, second_team.pk, token.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_team_tokens_delete(token_client, organizer, event, second_team, token):
    resp = token_client.delete(
        '/api/v1/organizers/{}/teams/{}/tokens/{}/'.format(organizer.slug, second_team.pk, token.pk))
    assert resp.status_code == 200
    token.refresh_from_db()
    assert not token.active


@pytest.mark.django_db
def test_team_token_create(token_client, organizer, event, second_team):
    resp = token_client.post('/api/v1/organizers/{}/teams/{}/tokens/'.format(organizer.slug, second_team.pk), {
        'name': 'New token'
    })
    assert resp.status_code == 201
    t = second_team.tokens.get()
    assert t.name == 'New token'
    assert t.active
    assert resp.data['token'] == t.token
