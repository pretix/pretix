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
        'software_version': '5.0.0'
    })
    assert resp.status_code == 200
    device.refresh_from_db()
    assert device.software_version == '5.0.0'


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
