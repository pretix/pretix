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
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Device, Event, Organizer, Team, User
from pretix.base.models.devices import generate_api_token


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
def device(organizer):
    return organizer.devices.create(name='Cashdesk', all_events=True)


@pytest.fixture
def admin_user(admin_team):
    u = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    admin_team.members.add(u)
    return u


@pytest.fixture
def admin_team(organizer):
    return Team.objects.create(organizer=organizer, can_change_organizer_settings=True, name='Admin team')


@pytest.mark.django_db
def test_list_of_devices(event, admin_user, client, device):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/devices')
    assert 'Cashdesk' in resp.content.decode()


@pytest.mark.django_db
def test_create_device(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.post('/control/organizer/dummy/device/add', {
        'name': 'Foo',
        'limit_events': str(event.pk),
        'security_profile': 'full',
    }, follow=True)
    with scopes_disabled():
        d = Device.objects.last()
        assert d.name == 'Foo'
        assert not d.all_events
        assert list(d.limit_events.all()) == [event]
        assert d.initialization_token in resp.content.decode()


@pytest.mark.django_db
def test_update_device(event, admin_user, admin_team, device, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/device/{}/edit'.format(device.pk), {
        'name': 'Cashdesk 2',
        'limit_events': str(event.pk),
        'security_profile': 'full',
    }, follow=True)
    device.refresh_from_db()
    assert device.name == 'Cashdesk 2'
    assert not device.all_events
    with scopes_disabled():
        assert list(device.limit_events.all()) == [event]


@pytest.mark.django_db
def test_revoke_device(event, admin_user, admin_team, device, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        device.api_token = generate_api_token()
    device.initialized = now()
    device.save()

    client.get('/control/organizer/dummy/device/{}/revoke'.format(device.pk))
    client.post('/control/organizer/dummy/device/{}/revoke'.format(device.pk), {}, follow=True)
    device.refresh_from_db()
    assert device.revoked


@pytest.mark.django_db
def test_revoke_device_before_initialization(event, admin_user, admin_team, device, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    device.save()

    client.get('/control/organizer/dummy/device/{}/revoke'.format(device.pk))
    client.post('/control/organizer/dummy/device/{}/revoke'.format(device.pk), {}, follow=True)
    device.refresh_from_db()
    assert device.revoked


@pytest.mark.django_db
def test_bulk_update_device(event, admin_user, admin_team, device, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/device/bulk_edit', {
        'device': str(device.pk),
        'bulkedit-limit_events': str(event.pk),
        '_bulk': ['bulkedit__events', 'bulkeditsecurity_profile'],
        'bulkedit-security_profile': 'full',
    }, follow=True)
    device.refresh_from_db()
    assert device.security_profile == 'full'
    assert not device.all_events
    with scopes_disabled():
        assert list(device.limit_events.all()) == [event]
