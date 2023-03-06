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
import time

import pytest

from pretix.base.models import Organizer


@pytest.mark.django_db
def test_no_auth(client):
    resp = client.get('/api/v1/organizers/')
    assert resp.status_code == 401


@pytest.mark.django_db
def test_session_auth_no_teams(client, user):
    client.login(email=user.email, password='dummy')
    resp = client.get('/api/v1/organizers/')
    assert resp.status_code == 200
    assert len(resp.data['results']) == 0


@pytest.mark.django_db
def test_session_auth_with_teams(client, user, team):
    team.members.add(user)
    Organizer.objects.create(name='Other dummy', slug='dummy2')
    client.login(email=user.email, password='dummy')
    resp = client.get('/api/v1/organizers/')
    assert resp.status_code == 200
    assert len(resp.data['results']) == 1


@pytest.mark.django_db
def test_session_auth_relative_timeout(client, user, team):
    client.login(email=user.email, password='dummy')
    session = client.session
    session['pretix_auth_long_session'] = False
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 6
    session['pretix_auth_last_used'] = int(time.time()) - 3600 * 3 - 60
    session.save()

    resp = client.get('/api/v1/organizers/')
    assert resp.status_code == 403


@pytest.mark.django_db
def test_token_invalid(client):
    client.credentials(HTTP_AUTHORIZATION='Token ABCDE')
    resp = client.get('/api/v1/organizers/')
    assert resp.status_code == 401


@pytest.mark.django_db
def test_token_auth_valid(client, team):
    Organizer.objects.create(name='Other dummy', slug='dummy2')
    t = team.tokens.create(name='Foo')
    client.credentials(HTTP_AUTHORIZATION='Token ' + t.token)
    resp = client.get('/api/v1/organizers/')
    assert resp.status_code == 200
    assert len(resp.data['results']) == 1


@pytest.mark.django_db
def test_token_auth_inactive(client, team):
    Organizer.objects.create(name='Other dummy', slug='dummy2')
    t = team.tokens.create(name='Foo', active=False)
    client.credentials(HTTP_AUTHORIZATION='Token ' + t.token)
    resp = client.get('/api/v1/organizers/')
    assert resp.status_code == 401


@pytest.mark.django_db
def test_device_invalid(client):
    client.credentials(HTTP_AUTHORIZATION='Device ABCDE')
    resp = client.get('/api/v1/organizers/')
    assert resp.status_code == 401


@pytest.mark.django_db
def test_device_auth_valid(client, device):
    client.credentials(HTTP_AUTHORIZATION='Device ' + device.api_token)
    resp = client.get('/api/v1/organizers/')
    assert resp.status_code == 200
    assert len(resp.data['results']) == 1


@pytest.mark.django_db
def test_device_auth_revoked(client, device):
    client.credentials(HTTP_AUTHORIZATION='Device ' + device.api_token)
    device.revoked = True
    device.save()
    resp = client.get('/api/v1/organizers/')
    assert resp.status_code == 401
    assert str(resp.data['detail']) == "Device access has been revoked."


@pytest.mark.django_db
def test_device_auth_security_profile(client, device):
    client.credentials(HTTP_AUTHORIZATION='Device ' + device.api_token)
    device.security_profile = "pretixscan"
    device.save()
    resp = client.get('/api/v1/organizers/dummy/giftcards/')
    assert resp.status_code == 403
    device.security_profile = "pretixpos"
    device.save()
    resp = client.get('/api/v1/organizers/dummy/giftcards/')
    assert resp.status_code == 200
