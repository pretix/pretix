import base64
import json
from urllib.parse import quote

import pytest

from pretix.api.models import (
    OAuthAccessToken, OAuthApplication, OAuthGrant, OAuthRefreshToken,
)
from pretix.base.models import Organizer, Team, User


@pytest.fixture
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
def admin_team(organizer):
    return Team.objects.create(organizer=organizer, can_change_teams=True, name='Admin team', all_events=True,
                               can_create_events=True)


@pytest.fixture
def admin_user(admin_team):
    u = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    admin_team.members.add(u)
    return u


@pytest.fixture
def application():
    return OAuthApplication.objects.create(
        name="pretalx",
        redirect_uris="https://pretalx.com",
        client_type='confidential',
        authorization_grant_type='authorization-code'
    )


@pytest.mark.django_db
def test_authorize_require_login(client, application: OAuthApplication):
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s' % (
        application.client_id, quote('https://example.org')
    ))
    assert resp.status_code == 302
    assert resp['Location'].startswith('/control/login')


@pytest.mark.django_db
def test_authorize_invalid_redirect_uri(client, admin_user, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s' % (
        application.client_id, quote('https://example.org')
    ))
    assert resp.status_code == 400


@pytest.mark.django_db
def test_authorize_missing_response_type(client, admin_user, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 302
    assert resp['Location'] == 'https://pretalx.com?error=invalid_request&error_description=Missing+response_type+parameter.'


@pytest.mark.django_db
def test_authorize_require_organizer(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ), data={
        'redirect_uri': application.redirect_uris,
        'scope': 'read write',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 200


@pytest.mark.django_db
def test_authorize_denied(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': str(organizer.pk),
        'redirect_uri': application.redirect_uris,
        'scope': 'read write',
        'client_id': application.client_id,
        'response_type': 'code',
    })
    assert resp.status_code == 302
    assert resp['Location'] == 'https://pretalx.com?error=access_denied'


@pytest.mark.django_db
def test_authorize_disallow_response_token(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=token' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 302
    assert resp['Location'] == 'https://pretalx.com?error=unauthorized_client'


@pytest.mark.django_db
def test_authorize_read_scope(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': str(organizer.pk),
        'redirect_uri': application.redirect_uris,
        'scope': 'read',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 302

    assert resp['Location'].startswith('https://pretalx.com?code=')
    code = resp['Location'].split("=")[1]
    grant = OAuthGrant.objects.get(code=code)
    assert list(grant.organizers.all()) == [organizer]
    assert grant.scope == "read"


@pytest.mark.django_db
def test_authorize_state(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code&state=asdadf' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': str(organizer.pk),
        'redirect_uri': application.redirect_uris,
        'scope': 'read',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
        'state': 'asdadf'
    })
    assert resp.status_code == 302
    assert 'state=asdadf' in resp['Location']


@pytest.mark.django_db
def test_authorize_default_scope(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': str(organizer.pk),
        'redirect_uri': application.redirect_uris,
        'scope': 'read write',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 302

    client.logout()
    assert resp['Location'].startswith('https://pretalx.com?code=')
    code = resp['Location'].split("=")[1]
    grant = OAuthGrant.objects.get(code=code)
    assert list(grant.organizers.all()) == [organizer]
    assert grant.scope == "read write"


@pytest.mark.django_db
def test_token_from_code_without_auth(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': str(organizer.pk),
        'redirect_uri': application.redirect_uris,
        'scope': 'read write',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 302
    assert resp['Location'].startswith('https://pretalx.com?code=')
    code = resp['Location'].split("=")[1]
    client.logout()
    resp = client.post('/api/v1/oauth/token', data={
        'code': code,
        'redirect_uri': application.redirect_uris,
        'grant_type': 'authorization_code',
    })
    assert resp.status_code == 401


@pytest.mark.django_db
def test_token_from_code(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': str(organizer.pk),
        'redirect_uri': application.redirect_uris,
        'scope': 'read write',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 302
    assert resp['Location'].startswith('https://pretalx.com?code=')
    code = resp['Location'].split("=")[1]
    client.logout()
    resp = client.post('/api/v1/oauth/token', data={
        'code': code,
        'redirect_uri': application.redirect_uris,
        'grant_type': 'authorization_code',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    data = json.loads(resp.content.decode())
    assert data['expires_in'] == 86400
    assert data['token_type'] == "Bearer"
    assert data['scope'] == "read write"
    access_token = data['access_token']
    grant = OAuthAccessToken.objects.get(token=access_token)
    assert list(grant.organizers.all()) == [organizer]


@pytest.mark.django_db
def test_use_token_for_access_one_organizer(client, admin_user, organizer, application: OAuthApplication):
    o2 = Organizer.objects.create(name='A', slug='a')
    t2 = Team.objects.create(organizer=o2, can_change_teams=True, name='Admin team', all_events=True)
    t2.members.add(admin_user)

    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': str(organizer.pk),
        'redirect_uri': application.redirect_uris,
        'scope': 'read write',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 302
    assert resp['Location'].startswith('https://pretalx.com?code=')
    code = resp['Location'].split("=")[1]
    client.logout()
    resp = client.post('/api/v1/oauth/token', data={
        'code': code,
        'redirect_uri': application.redirect_uris,
        'grant_type': 'authorization_code',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    data = json.loads(resp.content.decode())
    access_token = data['access_token']
    resp = client.get('/api/v1/organizers/', HTTP_AUTHORIZATION='Bearer %s' % access_token)
    assert resp.status_code == 200
    data = json.loads(resp.content.decode())
    assert data == {'count': 1, 'next': None, 'previous': None, 'results': [{'name': 'Dummy', 'slug': 'dummy'}]}
    resp = client.get('/api/v1/organizers/dummy/events/', HTTP_AUTHORIZATION='Bearer %s' % access_token)
    assert resp.status_code == 200
    resp = client.get('/api/v1/organizers/a/events/', HTTP_AUTHORIZATION='Bearer %s' % access_token)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_use_token_for_access_two_organizers(client, admin_user, organizer, application: OAuthApplication):
    o2 = Organizer.objects.create(name='A', slug='a')
    t2 = Team.objects.create(organizer=o2, can_change_teams=True, name='Admin team', all_events=True)
    t2.members.add(admin_user)

    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': [str(organizer.pk), str(o2.pk)],
        'redirect_uri': application.redirect_uris,
        'scope': 'read write',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 302
    assert resp['Location'].startswith('https://pretalx.com?code=')
    code = resp['Location'].split("=")[1]
    client.logout()
    resp = client.post('/api/v1/oauth/token', data={
        'code': code,
        'redirect_uri': application.redirect_uris,
        'grant_type': 'authorization_code',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    data = json.loads(resp.content.decode())
    access_token = data['access_token']
    resp = client.get('/api/v1/organizers/', HTTP_AUTHORIZATION='Bearer %s' % access_token)
    assert resp.status_code == 200
    data = json.loads(resp.content.decode())
    assert data == {'count': 2, 'next': None, 'previous': None, 'results': [
        {'name': 'A', 'slug': 'a'},
        {'name': 'Dummy', 'slug': 'dummy'},
    ]}
    resp = client.get('/api/v1/organizers/dummy/events/', HTTP_AUTHORIZATION='Bearer %s' % access_token)
    assert resp.status_code == 200
    resp = client.get('/api/v1/organizers/a/events/', HTTP_AUTHORIZATION='Bearer %s' % access_token)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_token_refresh(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': str(organizer.pk),
        'redirect_uri': application.redirect_uris,
        'scope': 'read write',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 302
    assert resp['Location'].startswith('https://pretalx.com?code=')
    code = resp['Location'].split("=")[1]
    client.logout()
    resp = client.post('/api/v1/oauth/token', data={
        'code': code,
        'redirect_uri': application.redirect_uris,
        'grant_type': 'authorization_code',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    data = json.loads(resp.content.decode())
    refresh_token = data['refresh_token']
    access_token = data['access_token']
    resp = client.post('/api/v1/oauth/token', data={
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    assert not OAuthAccessToken.objects.filter(token=access_token).exists()  # old token revoked
    data = json.loads(resp.content.decode())
    access_token = data['access_token']
    grant = OAuthAccessToken.objects.get(token=access_token)
    assert list(grant.organizers.all()) == [organizer]


@pytest.mark.django_db
def test_allow_write(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': [str(organizer.pk)],
        'redirect_uri': application.redirect_uris,
        'scope': 'read write',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 302
    assert resp['Location'].startswith('https://pretalx.com?code=')
    code = resp['Location'].split("=")[1]
    client.logout()
    resp = client.post('/api/v1/oauth/token', data={
        'code': code,
        'redirect_uri': application.redirect_uris,
        'grant_type': 'authorization_code',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    data = json.loads(resp.content.decode())
    access_token = data['access_token']
    resp = client.post('/api/v1/organizers/dummy/events/', HTTP_AUTHORIZATION='Bearer %s' % access_token)
    assert resp.status_code == 400


@pytest.mark.django_db
def test_allow_read_only(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': [str(organizer.pk)],
        'redirect_uri': application.redirect_uris,
        'scope': 'read',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 302
    assert resp['Location'].startswith('https://pretalx.com?code=')
    code = resp['Location'].split("=")[1]
    client.logout()
    resp = client.post('/api/v1/oauth/token', data={
        'code': code,
        'redirect_uri': application.redirect_uris,
        'grant_type': 'authorization_code',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    data = json.loads(resp.content.decode())
    access_token = data['access_token']
    resp = client.post('/api/v1/organizers/dummy/events/', HTTP_AUTHORIZATION='Bearer %s' % access_token)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_token_revoke_refresh_token(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': str(organizer.pk),
        'redirect_uri': application.redirect_uris,
        'scope': 'read write',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 302
    assert resp['Location'].startswith('https://pretalx.com?code=')
    code = resp['Location'].split("=")[1]
    client.logout()
    resp = client.post('/api/v1/oauth/token', data={
        'code': code,
        'redirect_uri': application.redirect_uris,
        'grant_type': 'authorization_code',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    data = json.loads(resp.content.decode())
    refresh_token = data['refresh_token']
    access_token = data['access_token']
    resp = client.post('/api/v1/oauth/revoke_token', data={
        'token': refresh_token,
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    assert not OAuthAccessToken.objects.get(token=access_token).is_valid()
    assert not OAuthRefreshToken.objects.filter(token=refresh_token, revoked__isnull=True).exists()
    resp = client.post('/api/v1/oauth/token', data={
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 400


@pytest.mark.django_db
def test_token_revoke_access_token(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': str(organizer.pk),
        'redirect_uri': application.redirect_uris,
        'scope': 'read write',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 302
    assert resp['Location'].startswith('https://pretalx.com?code=')
    code = resp['Location'].split("=")[1]
    client.logout()
    resp = client.post('/api/v1/oauth/token', data={
        'code': code,
        'redirect_uri': application.redirect_uris,
        'grant_type': 'authorization_code',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    data = json.loads(resp.content.decode())
    refresh_token = data['refresh_token']
    access_token = data['access_token']
    resp = client.post('/api/v1/oauth/revoke_token', data={
        'token': access_token,
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    assert not OAuthAccessToken.objects.get(token=access_token).is_valid()  # old token revoked

    resp = client.post('/api/v1/oauth/token', data={
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    data = json.loads(resp.content.decode())
    access_token = data['access_token']
    grant = OAuthAccessToken.objects.get(token=access_token)
    assert list(grant.organizers.all()) == [organizer]


@pytest.mark.django_db
def test_user_revoke(client, admin_user, organizer, application: OAuthApplication):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/api/v1/oauth/authorize?client_id=%s&redirect_uri=%s&response_type=code' % (
        application.client_id, quote(application.redirect_uris)
    ))
    assert resp.status_code == 200
    resp = client.post('/api/v1/oauth/authorize', data={
        'organizers': str(organizer.pk),
        'redirect_uri': application.redirect_uris,
        'scope': 'read write',
        'client_id': application.client_id,
        'response_type': 'code',
        'allow': 'Authorize',
    })
    assert resp.status_code == 302
    assert resp['Location'].startswith('https://pretalx.com?code=')
    code = resp['Location'].split("=")[1]
    client.logout()
    resp = client.post('/api/v1/oauth/token', data={
        'code': code,
        'redirect_uri': application.redirect_uris,
        'grant_type': 'authorization_code',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 200
    data = json.loads(resp.content.decode())
    refresh_token = data['refresh_token']
    access_token = data['access_token']

    at = OAuthAccessToken.objects.get(token=access_token)
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.post('/control/settings/oauth/authorized/{}/revoke'.format(at.pk), data={
    })
    assert resp.status_code == 302
    client.logout()
    assert not OAuthAccessToken.objects.filter(token=access_token).exists()
    assert OAuthRefreshToken.objects.get(token=refresh_token).revoked

    resp = client.post('/api/v1/oauth/token', data={
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
        ('%s:%s' % (application.client_id, application.client_secret)).encode()).decode())
    assert resp.status_code == 400
