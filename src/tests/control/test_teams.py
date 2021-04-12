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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Sohalt
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Event, Organizer, Team, User


@pytest.fixture
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
def event(organizer):
    event = Event.objects.create(
        organizer=organizer, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


@pytest.fixture
def admin_team(organizer):
    return Team.objects.create(organizer=organizer, can_change_teams=True, name='Admin team')


@pytest.fixture
def admin_user(admin_team):
    u = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    admin_team.members.add(u)
    return u


@pytest.mark.django_db
def test_list_of_teams(event, admin_user, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/teams')
    assert 'Admin team' in resp.content.decode()


@pytest.mark.django_db
def test_team_detail_view(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/team/{}/'.format(admin_team.pk))
    assert 'Admin team' in resp.content.decode()
    assert admin_user.email in resp.content.decode()


@pytest.mark.django_db
def test_team_add_user(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    u = User.objects.create_user('dummy2@dummy.dummy', 'dummy')

    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'user': u.email
    }, follow=True)
    assert 'Admin team' in resp.content.decode()
    assert admin_user.email in resp.content.decode()
    assert u.email in resp.content.decode()
    with scopes_disabled():
        assert u in admin_team.members.all()


@pytest.mark.django_db
def test_team_create_invite(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    djmail.outbox = []

    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'user': 'foo@example.org'
    }, follow=True)
    assert 'Admin team' in resp.content.decode()
    assert admin_user.email in resp.content.decode()
    assert 'foo@example.org' in resp.content.decode()
    with scopes_disabled():
        assert admin_team.invites.first().email == 'foo@example.org'
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_team_create_token(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    djmail.outbox = []

    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'name': 'Test token'
    }, follow=True)
    assert 'Test token' in resp.content.decode()
    with scopes_disabled():
        assert admin_team.tokens.first().name == 'Test token'
        assert admin_team.tokens.first().token in resp.content.decode()


@pytest.mark.django_db
def test_team_remove_token(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    with scopes_disabled():
        tk = admin_team.tokens.create(name='Test token')
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-token': str(tk.pk)
    }, follow=True)
    assert tk.token not in resp.content.decode()
    assert 'Test token' in resp.content.decode()
    tk.refresh_from_db()
    assert not tk.active


@pytest.mark.django_db
def test_team_resend_invite(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    djmail.outbox = []

    inv = admin_team.invites.create(email='foo@example.org')
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'resend-invite': str(inv.pk)
    }, follow=True)
    assert 'Admin team' in resp.content.decode()
    assert admin_user.email in resp.content.decode()
    assert 'foo@example.org' in resp.content.decode()
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_team_revoke_invite(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    with scopes_disabled():
        inv = admin_team.invites.create(email='foo@example.org')
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-invite': str(inv.pk)
    }, follow=True)
    assert 'Admin team' in resp.content.decode()
    assert admin_user.email in resp.content.decode()
    with scopes_disabled():
        assert not admin_team.invites.exists()


@pytest.mark.django_db
def test_team_remove_user(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    u = User.objects.create_user('dummy2@dummy.dummy', 'dummy')
    with scopes_disabled():
        admin_team.members.add(u)

    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-member': u.pk
    }, follow=True)
    assert 'Admin team' in resp.content.decode()
    assert admin_user.email in resp.content.decode()
    with scopes_disabled():
        assert u not in admin_team.members.all()


@pytest.mark.django_db
def test_team_remove_last_admin(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-member': admin_user.pk
    }, follow=True)
    assert 'alert-danger' in resp.content.decode()
    with scopes_disabled():
        assert admin_user in admin_team.members.all()

    t2 = Team.objects.create(organizer=event.organizer, name='Admin team 2')
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-member': admin_user.pk
    }, follow=True)
    assert 'alert-danger' in resp.content.decode()
    with scopes_disabled():
        assert admin_user in admin_team.members.all()

    t2.members.add(admin_user)
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-member': admin_user.pk
    }, follow=True)
    assert 'alert-danger' in resp.content.decode()
    with scopes_disabled():
        assert admin_user in admin_team.members.all()

    t2.can_change_teams = True
    t2.save()
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-member': admin_user.pk
    }, follow=True)
    assert 'alert-danger' not in resp.content.decode()
    with scopes_disabled():
        assert admin_user not in admin_team.members.all()


@pytest.mark.django_db
def test_create_team(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/team/add', {
        'name': 'Foo',
        'can_create_events': 'on',
        'limit_events': str(event.pk),
        'can_change_event_settings': 'on'
    }, follow=True)
    with scopes_disabled():
        t = Team.objects.last()
        assert t.can_change_event_settings
        assert t.can_create_events
        assert not t.can_change_organizer_settings
        assert list(t.limit_events.all()) == [event]
        assert list(t.members.all()) == [admin_user]


@pytest.mark.django_db
def test_update_team(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/team/{}/edit'.format(admin_team.pk), {
        'name': 'Admin',
        'can_change_teams': 'on',
        'limit_events': str(event.pk),
        'can_change_event_settings': 'on'
    }, follow=True)
    admin_team.refresh_from_db()
    assert admin_team.can_change_event_settings
    assert not admin_team.can_change_organizer_settings
    with scopes_disabled():
        assert list(admin_team.limit_events.all()) == [event]


@pytest.mark.django_db
def test_update_last_team_to_be_no_admin(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.post('/control/organizer/dummy/team/{}/edit'.format(admin_team.pk), {
        'name': 'Admin',
        'can_change_event_settings': 'on'
    }, follow=True)
    assert 'alert-danger' in resp.content.decode()


@pytest.mark.django_db
def test_remove_team(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    with scopes_disabled():
        t2 = Team.objects.create(organizer=event.organizer, name='Admin team 2')
    resp = client.post('/control/organizer/dummy/team/{}/delete'.format(t2.pk), {}, follow=True)
    with scopes_disabled():
        assert Team.objects.count() == 1
    assert 'alert-success' in resp.content.decode()


@pytest.mark.django_db
def test_remove_last_admin_team(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    resp = client.post('/control/organizer/dummy/team/{}/delete'.format(admin_team.pk), {}, follow=True)
    with scopes_disabled():
        assert Team.objects.count() == 1
    assert 'alert-danger' in resp.content.decode()


@pytest.mark.django_db
def test_resend_invalid_invite(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    djmail.outbox = []

    with scopes_disabled():
        inv = admin_team.invites.create(email='foo@example.org')
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'resend-invite': inv.pk + 1
    }, follow=True)
    assert b'alert-danger' in resp.content
    assert b'Invalid invite selected.' in resp.content
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_invite_invalid_token(event, admin_team, client):
    with scopes_disabled():
        i = admin_team.invites.create(email='foo@bar.com')
    resp = client.get('/control/invite/foo{}bar'.format(i.token), follow=True)
    assert b'alert-danger' in resp.content
    assert b'invalid link' in resp.content


@pytest.mark.django_db
def test_invite_existing_team_member(event, admin_team, client):
    u = User.objects.create_user('dummy2@dummy.dummy', 'dummy')
    with scopes_disabled():
        admin_team.members.add(u)
        client.login(email='dummy2@dummy.dummy', password='dummy')
        i = admin_team.invites.create(email='foo@bar.com')
    resp = client.get('/control/invite/{}'.format(i.token), follow=True)
    assert b'alert-danger' in resp.content
    assert b'already are part of' in resp.content


@pytest.mark.django_db
def test_invite_authenticated(event, admin_team, client):
    u = User.objects.create_user('dummy2@dummy.dummy', 'dummy')
    client.login(email='dummy2@dummy.dummy', password='dummy')
    with scopes_disabled():
        i = admin_team.invites.create(email='foo@bar.com')
    resp = client.get('/control/invite/{}'.format(i.token), follow=True)
    assert b'alert-success' in resp.content
    with scopes_disabled():
        assert u in admin_team.members.all()
        assert not admin_team.invites.exists()


@pytest.mark.django_db
def test_invite_new_user(event, admin_team, client):
    with scopes_disabled():
        i = admin_team.invites.create(email='foo@bar.com')
    resp = client.get('/control/invite/{}'.format(i.token), follow=True)
    assert b'<form' in resp.content
    resp = client.post('/control/invite/{}'.format(i.token), {
        'email': 'dummy@example.org',
        'password': 'asdsdgfgjh',
        'password_repeat': 'asdsdgfgjh'
    }, follow=True)

    assert b'alert-success' in resp.content
    with scopes_disabled():
        assert admin_team.members.filter(email='dummy@example.org').exists()
        assert not admin_team.invites.exists()
