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
