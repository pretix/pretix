#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
from django.test import RequestFactory
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import Event, Organizer, Team, User
from pretix.multidomain.middlewares import SessionMiddleware


@pytest.fixture
def organizer():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    with scope(organizer=o):
        yield o


@pytest.fixture
def event(organizer):
    event = Event.objects.create(
        organizer=organizer, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


@pytest.fixture
def user():
    return User.objects.create_user('dummy@dummy.dummy', 'dummy')


@pytest.fixture
def admin():
    u = User.objects.create_user('admin@dummy.dummy', 'dummy', is_staff=True)
    return u


@pytest.fixture
def admin_request(admin, client):
    factory = RequestFactory()
    r = factory.get('/')
    SessionMiddleware(NotImplementedError).process_request(r)
    r.session.save()
    admin.staffsession_set.create(date_start=now(), session_key=r.session.session_key)
    admin.staffsession_set.create(date_start=now(), session_key=client.session.session_key)
    return r


@pytest.mark.django_db
def test_any_event_permission_limited(event, user):
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event)

    team = Team.objects.create(organizer=event.organizer)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event)

    team.members.add(user)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event)
    assert not team.permission_for_event(event)

    team.limit_events.add(event)
    user._teamcache = {}
    assert team.permission_for_event(event)
    assert user.has_event_permission(event.organizer, event)


@pytest.mark.django_db
def test_any_event_permission_all(event, user):
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event)

    team = Team.objects.create(organizer=event.organizer)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event)

    team.members.add(user)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event)
    assert not team.permission_for_event(event)

    team.all_events = True
    team.save()
    user._teamcache = {}
    assert team.permission_for_event(event)
    assert user.has_event_permission(event.organizer, event)


@pytest.mark.django_db
def test_specific_event_permission_limited(event, user):
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'event.orders:write')

    team = Team.objects.create(organizer=event.organizer, limit_event_permissions={"event.orders:write": True})
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'event.orders:write')

    team.members.add(user)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'event.orders:write')

    team.limit_events.add(event)
    user._teamcache = {}
    assert user.has_event_permission(event.organizer, event, 'event.orders:write')
    assert not user.has_event_permission(event.organizer, event, 'event.settings.general:write')

    assert user.has_event_permission(event.organizer, event, ('event.orders:write', 'event.settings.general:write'))
    assert not user.has_event_permission(event.organizer, event, ('organizer.teams:write', 'event.settings.general:write'))

    team.limit_event_permissions = {}
    team.save()
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'event.orders:write')


@pytest.mark.django_db
def test_specific_event_permission_all(event, user):
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'event.orders:write')

    team = Team.objects.create(organizer=event.organizer, limit_event_permissions={"event.orders:write": True})
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'event.orders:write')

    team.members.add(user)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'event.orders:write')

    team.all_events = True
    team.save()
    user._teamcache = {}
    assert user.has_event_permission(event.organizer, event, 'event.orders:write')

    team.limit_event_permissions = {}
    team.save()
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'event.orders:write')


@pytest.mark.django_db
def test_event_permissions_multiple_teams(event, user):
    team1 = Team.objects.create(organizer=event.organizer, limit_event_permissions={"event.orders:write": True}, all_events=True)
    team2 = Team.objects.create(organizer=event.organizer, limit_event_permissions={"event.vouchers:write": True})
    team3 = Team.objects.create(organizer=event.organizer, limit_event_permissions={"event.settings.general:write": True})
    event2 = Event.objects.create(
        organizer=event.organizer, name='Dummy', slug='dummy2',
        date_from=now()
    )
    team1.members.add(user)
    team2.members.add(user)
    team3.members.add(user)
    team2.limit_events.add(event)
    team3.limit_events.add(event2)

    assert user.has_event_permission(event.organizer, event, 'event.orders:write')
    assert user.has_event_permission(event.organizer, event, 'event.vouchers:write')
    assert not user.has_event_permission(event.organizer, event, 'event.settings.general:write')
    assert user.get_event_permission_set(event.organizer, event) == {
        'event.orders:write', 'event.vouchers:write',
        'can_change_orders', 'can_change_vouchers',
    }
    assert user.get_event_permission_set(event.organizer, event2) == {
        'event.orders:write', 'event.settings.general:write', 'event.settings.general:write',
        'can_change_orders', 'can_change_event_settings',
    }


@pytest.mark.django_db
def test_any_organizer_permission(event, user):
    user._teamcache = {}
    assert not user.has_organizer_permission(event.organizer)

    team = Team.objects.create(organizer=event.organizer)
    user._teamcache = {}
    assert not user.has_organizer_permission(event.organizer)

    team.members.add(user)
    user._teamcache = {}
    assert user.has_organizer_permission(event.organizer)


@pytest.mark.django_db
def test_specific_organizer_permission(event, user):
    user._teamcache = {}
    assert not user.has_organizer_permission(event.organizer, 'organizer.events:create')

    team = Team.objects.create(organizer=event.organizer, limit_organizer_permissions={"organizer.events:create": True})
    user._teamcache = {}
    assert not user.has_organizer_permission(event.organizer, 'organizer.events:create')

    team.members.add(user)
    user._teamcache = {}
    assert user.has_organizer_permission(event.organizer, 'organizer.events:create')
    assert user.has_organizer_permission(event.organizer, ('organizer.events:create', 'organizer.settings.general:write'))


@pytest.mark.django_db
def test_organizer_permissions_multiple_teams(event, user):
    team1 = Team.objects.create(organizer=event.organizer, limit_organizer_permissions={"organizer.settings.general:write": True})
    team2 = Team.objects.create(organizer=event.organizer, limit_organizer_permissions={"organizer.events:create": True})
    team1.members.add(user)
    team2.members.add(user)
    orga2 = Organizer.objects.create(slug='d2', name='d2')
    team3 = Team.objects.create(organizer=orga2, limit_organizer_permissions={"organizer.teams:write": True})
    team3.members.add(user)

    assert user.has_organizer_permission(event.organizer, 'organizer.events:create')
    assert user.has_organizer_permission(event.organizer, 'organizer.settings.general:write')
    assert not user.has_organizer_permission(event.organizer, 'organizer.teams:write')
    assert user.get_organizer_permission_set(event.organizer) == {
        'organizer.events:create', 'organizer.settings.general:write',
        'can_create_events', 'can_change_organizer_settings',
    }
    assert user.get_organizer_permission_set(orga2) == {
        'organizer.teams:write',
        'can_change_teams',
    }


@pytest.mark.django_db
def test_superuser(event, admin, admin_request):
    assert admin.has_organizer_permission(event.organizer, request=admin_request)
    assert admin.has_organizer_permission(event.organizer, 'organizer.events:create', request=admin_request)
    assert admin.has_event_permission(event.organizer, event, request=admin_request)
    assert admin.has_event_permission(event.organizer, event, 'event.settings.general:write', request=admin_request)

    assert 'arbitrary' not in admin.get_event_permission_set(event.organizer, event)
    assert 'arbitrary' not in admin.get_organizer_permission_set(event.organizer)

    assert event in admin.get_events_with_any_permission(request=admin_request)


@pytest.mark.django_db
def test_list_of_events(event, user, admin, admin_request):
    orga2 = Organizer.objects.create(slug='d2', name='d2')
    event2 = Event.objects.create(
        organizer=event.organizer, name='Dummy', slug='dummy2',
        date_from=now()
    )
    event3 = Event.objects.create(
        organizer=orga2, name='Dummy', slug='dummy3',
        date_from=now()
    )
    event4 = Event.objects.create(
        organizer=orga2, name='Dummy', slug='dummy4',
        date_from=now()
    )
    User.objects.filter(email="admin@localhost").delete()

    assert not user.get_events_with_any_permission()

    team1 = Team.objects.create(organizer=event.organizer, limit_event_permissions={"event.orders:write": True}, all_events=True)
    team2 = Team.objects.create(organizer=event.organizer, limit_event_permissions={"event.vouchers:write": True})
    team3 = Team.objects.create(organizer=orga2, limit_event_permissions={"event.settings.general:write": True})
    team1.members.add(user)
    team2.members.add(user)
    team3.members.add(user)
    team2.limit_events.add(event)
    team3.limit_events.add(event3)

    with scope(organizer=[event.organizer, orga2]):
        events = list(user.get_events_with_any_permission(request=admin_request))
        assert event in events
        assert event2 in events
        assert event3 in events
        assert event4 not in events

        events = list(user.get_events_with_permission('event.settings.general:write', request=admin_request))
        assert event not in events
        assert event2 not in events
        assert event3 in events
        assert event4 not in events

        assert set(event.get_users_with_any_permission()) == {user}
        assert set(event2.get_users_with_any_permission()) == {user}
        assert set(event3.get_users_with_any_permission()) == {user}
        assert set(event4.get_users_with_any_permission()) == set()

        assert set(event.get_users_with_permission('event.settings.general:write')) == set()
        assert set(event2.get_users_with_permission('event.settings.general:write')) == set()
        assert set(event3.get_users_with_permission('event.settings.general:write')) == {user}
        assert set(event4.get_users_with_permission('event.settings.general:write')) == set()
        assert set(event.get_users_with_permission('event.orders:write')) == {user}
