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

from pretix.base.models import Device


@pytest.fixture
def new_device(organizer):
    return Device.objects.create(
        name="Foo",
        all_events=True,
        organizer=organizer
    )


@pytest.mark.django_db
def test_initialize_required_fields(client, new_device: Device):
    resp = client.post('/api/v1/device/initialize')
    assert resp.status_code == 400
    assert resp.data == {
        'token': ['This field is required.'],
        'hardware_brand': ['This field is required.'],
        'hardware_model': ['This field is required.'],
        'software_brand': ['This field is required.'],
        'software_version': ['This field is required.'],
    }


@pytest.mark.django_db
def test_initialize_unknown_token(client, new_device: Device):
    resp = client.post('/api/v1/device/initialize', {
        'token': 'aaa',
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '4.0.0'
    })
    assert resp.status_code == 400
    assert resp.data == {'token': ['Unknown initialization token.']}


@pytest.mark.django_db
def test_initialize_used_token(client, device: Device):
    resp = client.post('/api/v1/device/initialize', {
        'token': device.initialization_token,
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '4.0.0'
    })
    assert resp.status_code == 400
    assert resp.data == {'token': ['This initialization token has already been used.']}


@pytest.mark.django_db
def test_initialize_revoked_token(client, new_device: Device):
    new_device.revoked = True
    new_device.save()
    resp = client.post('/api/v1/device/initialize', {
        'token': new_device.initialization_token,
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '4.0.0'
    })
    assert resp.status_code == 400
    assert resp.data == {'token': ['This initialization token has been revoked.']}


@pytest.mark.django_db
def test_initialize_valid_token(client, new_device: Device):
    resp = client.post('/api/v1/device/initialize', {
        'token': new_device.initialization_token,
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '4.0.0'
    })
    assert resp.status_code == 200
    assert resp.data['organizer'] == 'dummy'
    assert resp.data['name'] == 'Foo'
    assert 'device_id' in resp.data
    assert 'unique_serial' in resp.data
    assert 'api_token' in resp.data
    new_device.refresh_from_db()
    assert new_device.api_token
    assert new_device.initialized


@pytest.mark.django_db
def test_update_required_fields(device_client, device: Device):
    resp = device_client.post('/api/v1/device/update')
    assert resp.status_code == 400
    assert resp.data == {
        'hardware_brand': ['This field is required.'],
        'hardware_model': ['This field is required.'],
        'software_brand': ['This field is required.'],
        'software_version': ['This field is required.'],
    }


@pytest.mark.django_db
def test_update_required_auth(client, token_client, device: Device):
    resp = client.post('/api/v1/device/update', {
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '5.0.0'
    })
    assert resp.status_code == 401
    resp = token_client.post('/api/v1/device/update', {
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '5.0.0'
    })
    assert resp.status_code == 401


@pytest.mark.django_db
def test_update_valid_fields(device_client, device: Device):
    resp = device_client.post('/api/v1/device/update', {
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '5.0.0',
        'info': {
            'foo': 'bar'
        },
    }, format='json')
    assert resp.status_code == 200
    device.refresh_from_db()
    assert device.software_version == '5.0.0'
    assert device.info == {'foo': 'bar'}


@pytest.mark.django_db
def test_keyroll_required_auth(client, token_client, device: Device):
    resp = client.post('/api/v1/device/roll', {})
    assert resp.status_code == 401
    resp = token_client.post('/api/v1/device/roll', {})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_keyroll_valid(device_client, device: Device):
    token = device.api_token
    resp = device_client.post('/api/v1/device/roll')
    assert resp.status_code == 200
    device.refresh_from_db()
    assert device.api_token
    assert device.api_token != token


@pytest.mark.django_db
def test_revoke_required_auth(client, token_client, device: Device):
    resp = client.post('/api/v1/device/revoke', {})
    assert resp.status_code == 401
    resp = token_client.post('/api/v1/device/revoke', {})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_revoke_valid(device_client, device: Device):
    resp = device_client.post('/api/v1/device/revoke')
    assert resp.status_code == 200
    device.refresh_from_db()
    assert device.revoked


@pytest.mark.django_db
def test_device_info(device_client, device: Device):
    resp = device_client.get('/api/v1/device/info')
    assert resp.status_code == 200
    assert resp.data['device']['organizer'] == 'dummy'
    assert resp.data['device']['name'] == 'Foo'
    assert 'device_id' in resp.data['device']
    assert 'unique_serial' in resp.data['device']
    assert 'api_token' in resp.data['device']
    assert 'pretix' in resp.data['server']['version']
