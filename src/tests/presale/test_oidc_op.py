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
import base64
import json
import re
import time
from binascii import hexlify
from datetime import timedelta
from urllib.parse import quote

import jwt
import pytest
from bs4 import BeautifulSoup
from Crypto.PublicKey import RSA
from django.utils.timezone import now
from django_scopes import scopes_disabled
from freezegun import freeze_time
from tests.base import extract_form_fields

from pretix.base.customersso.oidc import _hash_scheme
from pretix.base.models import Event, Organizer
from pretix.base.models.customers import (
    CustomerSSOAccessToken, CustomerSSOClient,
)


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Big Events LLC', slug='bigevents')
    o.settings.customer_accounts = True
    o.settings.customer_accounts_native = True
    event = Event.objects.create(
        organizer=o, name='Conference', slug='conf',
        date_from=now() + timedelta(days=10),
        live=True, is_public=False
    )
    customer = o.customers.create(email='john@example.org', is_verified=True, identifier="ABC123",
                                  name_parts={'_scheme': 'given_family', 'given_name': 'John', 'family_name': 'Doe'},
                                  phone='+49302270')
    customer.set_password('foo')
    customer.save()
    return o, event


@pytest.fixture
def ssoclient(env, client):
    c = CustomerSSOClient(organizer=env[0], name="Test",
                          redirect_uris="https://example.net https://example.org/path?query=value#hash=foo")
    secret = c.set_client_secret()
    c.save()
    return c, secret


@pytest.mark.django_db
def test_authorize_final_errors(env, client, ssoclient):
    r = client.get('/bigevents/oauth2/v1/authorize')
    assert r.status_code == 400
    assert b'client_id missing' in r.content

    r = client.get('/bigevents/oauth2/v1/authorize?client_id=abc')
    assert r.status_code == 400
    assert b'invalid client_id' in r.content

    r = client.get(f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&response_type=code')
    assert r.status_code == 400
    assert b'invalid redirect_uri' in r.content

    r = client.get(f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&redirect_uri=https://google.com')
    assert r.status_code == 400
    assert b'invalid redirect_uri' in r.content

    r = client.get(
        f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&'
        f'redirect_uri={quote("https://example.org/path?query=value#hash=foo")}&scope=openid+profile'
    )
    assert r.status_code == 400
    assert b"response_type unsupported" in r.content

    r = client.get(
        f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&response_type=id_token&response_mode=query&'
        f'redirect_uri={quote("https://example.org/path?query=value#hash=foo")}&scope=openid+profile'
    )
    assert r.status_code == 400
    assert b"response_mode query" in r.content

    r = client.get(
        f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&response_type=id_token&response_mode=bogus'
        f'&redirect_uri=https://example.net')
    assert r.status_code == 400
    assert b'invalid response_mode' in r.content


@pytest.mark.django_db
def test_authorize_basic_redirect_errors(env, client, ssoclient):
    r = client.get(
        f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&redirect_uri=https://example.net&response_type=code')
    assert r.status_code == 302
    assert r.headers['Location'] == 'https://example.net?error=invalid_scope&' \
                                    'error_description=scope+%27openid%27+must+be+requested'

    r = client.get(
        f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&redirect_uri=https://example.net&response_type=id_token'
        f'&scope=openid+email')
    assert r.status_code == 302
    assert r.headers['Location'] == 'https://example.net#error=invalid_request&' \
                                    'error_description=nonce+is+required+in+implicit+or+hybrid+flow'


@pytest.mark.django_db
def test_authorize_redirect_post_to_get(env, client, ssoclient):
    r = client.post('/bigevents/oauth2/v1/authorize', {
        'client_id': ssoclient[0].client_id,
        'redirect_uri': 'https://example.net',
        'response_type': 'code',
        'scope': 'openid+profile',
    })
    assert r.status_code == 302
    assert r.headers['Location'] == f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&' \
                                    f'redirect_uri=https%3A%2F%2Fexample.net&response_type=code&scope=openid%2Bprofile'


@pytest.mark.django_db
def test_authorize_success_with_login(env, client, ssoclient):
    url = f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&' \
          f'redirect_uri=https://example.net&' \
          f'response_type=code&' \
          f'state=STATE&' \
          f'scope=openid+profile'
    r = client.get(url)
    assert r.status_code == 200
    assert b'login-email' in r.content

    doc = BeautifulSoup(r.content, "lxml")
    d = extract_form_fields(doc)
    d.update({
        'login-email': 'john@example.org',
        'login-password': 'foo',
    })

    r = client.post(url, d)
    assert r.status_code == 302
    assert re.match(r'https://example.net\?code=([a-z0-9A-Z]{64})&state=STATE', r.headers['Location'])


@pytest.mark.django_db
def test_authorize_success_with_existing_session(env, client, ssoclient):
    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 302

    url = f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&' \
          f'redirect_uri=https://example.net&' \
          f'response_type=code&' \
          f'state=STATE&' \
          f'scope=openid+profile'
    r = client.get(url)
    assert r.status_code == 302
    assert re.match(r'https://example.net\?code=([a-z0-9A-Z]{64})&state=STATE', r.headers['Location'])


@pytest.mark.django_db
def test_authorize_with_prompt_none(env, client, ssoclient):
    url = f'/bigevents/oauth2/v1/authorize?' \
          f'prompt=none&' \
          f'client_id={ssoclient[0].client_id}&' \
          f'redirect_uri=https://example.net&' \
          f'response_type=code&state=STATE&scope=openid+profile'
    r = client.get(url)
    assert r.status_code == 302
    assert r.headers['Location'] == 'https://example.net?' \
                                    'error=interaction_required&' \
                                    'error_description=user+is+not+logged+in+but+no+prompt+is+allowed&' \
                                    'state=STATE'
    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 302

    url = f'/bigevents/oauth2/v1/authorize?' \
          f'prompt=none&' \
          f'client_id={ssoclient[0].client_id}&' \
          f'redirect_uri=https://example.net&' \
          f'response_type=code&state=STATE&scope=openid+profile'
    r = client.get(url)
    assert r.status_code == 302
    assert re.match(r'https://example.net\?code=([a-z0-9A-Z]{64})&state=STATE', r.headers['Location'])


@pytest.mark.django_db
def test_authorize_require_login_if_prompt_requires_it_or_is_expired(env, client, ssoclient):
    with freeze_time("2021-04-10T11:00:00+02:00"):
        r = client.post('/bigevents/account/login', {
            'email': 'john@example.org',
            'password': 'foo',
        })
        assert r.status_code == 302

        url = f'/bigevents/oauth2/v1/authorize?' \
              f'prompt=login&' \
              f'client_id={ssoclient[0].client_id}&' \
              f'redirect_uri=https://example.net&' \
              f'response_type=code&state=STATE&scope=openid+profile'
        r = client.get(url)
        assert r.status_code == 200
        assert b'login-email' in r.content

    with freeze_time("2021-04-10T11:59:00+02:00"):
        url = f'/bigevents/oauth2/v1/authorize?' \
              f'max_age=3600&' \
              f'client_id={ssoclient[0].client_id}&' \
              f'redirect_uri=https://example.net&' \
              f'response_type=code&state=STATE&scope=openid+profile'
        r = client.get(url)
        assert r.status_code == 302

    with freeze_time("2021-04-10T12:01:00+02:00"):
        url = f'/bigevents/oauth2/v1/authorize?' \
              f'max_age=3600&' \
              f'client_id={ssoclient[0].client_id}&' \
              f'redirect_uri=https://example.net&' \
              f'response_type=code&state=STATE&scope=openid+profile'
        r = client.get(url)
        assert r.status_code == 200
        assert b'login-email' in r.content


@pytest.mark.django_db
def test_token_require_client_id(env, client, ssoclient):
    r = client.post('/bigevents/oauth2/v1/token', {
    })
    assert r.status_code == 400
    assert b'invalid_client' in r.content

    r = client.post('/bigevents/oauth2/v1/token', {
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode('wrong:wrong'.encode()).decode())
    assert r.status_code == 401
    assert b'invalid_client' in r.content
    assert 'invalid_client' in r.headers['WWW-Authenticate']

    r = client.post('/bigevents/oauth2/v1/token', {
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(f'{ssoclient[0].client_id}:wrong'.encode()).decode())
    assert r.status_code == 401
    assert b'invalid_client' in r.content
    assert 'invalid_client' in r.headers['WWW-Authenticate']

    r = client.post('/bigevents/oauth2/v1/token', {
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(f'{ssoclient[0].client_id}:{ssoclient[1]}'.encode()).decode())
    assert r.status_code == 400
    assert b'unsupported_grant_type' in r.content

    r = client.post('/bigevents/oauth2/v1/token', {
        'client_id': ssoclient[0].client_id
    })
    assert r.status_code == 400
    assert b'confidential' in r.content

    ssoclient[0].client_type = CustomerSSOClient.CLIENT_PUBLIC
    ssoclient[0].save()

    r = client.post('/bigevents/oauth2/v1/token', {
        'client_id': ssoclient[0].client_id
    })
    assert r.status_code == 400
    assert b'unsupported_grant_type' in r.content


def _authorization_step(client, ssoclient):
    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 302

    url = f'/bigevents/oauth2/v1/authorize?' \
          f'prompt=none&' \
          f'nonce=NONCE123&' \
          f'client_id={ssoclient[0].client_id}&' \
          f'redirect_uri=https://example.net&' \
          f'response_type=code&state=STATE&scope=openid+profile+email+phone'
    r = client.get(url)
    assert r.status_code == 302
    m = re.match(r'https://example.net\?code=([a-z0-9A-Z]{64})&state=STATE', r.headers['Location'])
    assert m
    return m.group(1)


@pytest.mark.django_db
def test_token_missing_or_mismatching_parameters(env, client, ssoclient):
    code = _authorization_step(client, ssoclient)

    r = client.post('/bigevents/oauth2/v1/token', {
        'grant_type': 'test'
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(f'{ssoclient[0].client_id}:{ssoclient[1]}'.encode()).decode())
    assert r.status_code == 400
    assert b'unsupported_grant_type' in r.content

    r = client.post('/bigevents/oauth2/v1/token', {
        'grant_type': 'authorization_code',
        'code': 'fail',
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(f'{ssoclient[0].client_id}:{ssoclient[1]}'.encode()).decode())
    assert r.status_code == 400
    assert b'Unknown or expired authorization code' in r.content

    r = client.post('/bigevents/oauth2/v1/token', {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': 'https://google.com'
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(f'{ssoclient[0].client_id}:{ssoclient[1]}'.encode()).decode())
    assert r.status_code == 400
    assert b'Mismatch of redirect_uri' in r.content


@pytest.mark.django_db
def test_token_success(env, client, ssoclient):
    code = _authorization_step(client, ssoclient)

    r = client.post('/bigevents/oauth2/v1/token', {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': 'https://example.net'
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(f'{ssoclient[0].client_id}:{ssoclient[1]}'.encode()).decode())
    assert r.status_code == 200
    d = json.loads(r.content)
    assert d['access_token']
    assert d['token_type'].lower() == 'bearer'
    assert 86390 < d['expires_in'] <= 86400
    token = d['id_token']

    env[0].settings.flush()
    decoded = jwt.decode(token, env[0].settings.sso_server_signing_key_rsa256_public, algorithms=["RS256"],
                         audience=ssoclient[0].client_id)
    assert decoded['iss'] == 'http://example.com/bigevents'
    assert decoded['aud'] == ssoclient[0].client_id
    assert decoded['sub'] == "ABC123"
    assert time.time() + 86390 < decoded['exp'] <= time.time() + 86400
    assert time.time() - 10 < decoded['iat'] <= time.time()
    assert time.time() - 10 < decoded['auth_time'] <= time.time()
    assert 'email' not in decoded
    assert decoded['nonce'] == 'NONCE123'

    # Assert that code can only be used once
    r = client.post('/bigevents/oauth2/v1/token', {
        'grant_type': 'code',
        'code': code,
        'redirect_uri': 'https://example.net'
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(f'{ssoclient[0].client_id}:{ssoclient[1]}'.encode()).decode())
    assert r.status_code == 400

    # Assert that auth token is revoked after reuse
    with scopes_disabled():
        CustomerSSOAccessToken.objects.get(token=d['access_token']).expires < now()


@pytest.mark.django_db
def test_scope_enforcement(env, client, ssoclient):
    ssoclient[0].allowed_scopes = ['openid', 'profile']
    ssoclient[0].save()
    code = _authorization_step(client, ssoclient)

    r = client.post('/bigevents/oauth2/v1/token', {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': 'https://example.net'
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(f'{ssoclient[0].client_id}:{ssoclient[1]}'.encode()).decode())
    assert r.status_code == 200
    d = json.loads(r.content)
    token = d['id_token']
    env[0].settings.flush()
    decoded = jwt.decode(token, env[0].settings.sso_server_signing_key_rsa256_public, algorithms=["RS256"],
                         audience=ssoclient[0].client_id)
    assert 'email' not in decoded
    assert decoded['nonce'] == 'NONCE123'


@pytest.mark.django_db
def test_token_client_secret_post(env, client, ssoclient):
    code = _authorization_step(client, ssoclient)

    r = client.post('/bigevents/oauth2/v1/token', {
        'client_id': ssoclient[0].client_id,
        'client_secret': ssoclient[1],
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': 'https://example.net'
    })
    assert r.status_code == 200
    d = json.loads(r.content)
    assert d['access_token']
    assert d['token_type'].lower() == 'bearer'
    assert 86390 < d['expires_in'] <= 86400


@pytest.mark.django_db
def test_authorize_implicit_flow(env, client, ssoclient):
    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 302

    url = f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&' \
          f'redirect_uri=https://example.net&' \
          f'response_type=id_token&' \
          f'state=STATE&' \
          f'nonce=NONCE123&' \
          f'scope=openid+profile+email'
    r = client.get(url)
    assert r.status_code == 302
    match = re.match(r'https://example.net#id_token=([^&]+)&state=STATE', r.headers['Location'])
    assert match

    env[0].settings.flush()
    decoded = jwt.decode(match.group(1), env[0].settings.sso_server_signing_key_rsa256_public, algorithms=["RS256"],
                         audience=ssoclient[0].client_id)
    assert decoded['iss'] == 'http://example.com/bigevents'
    assert decoded['aud'] == ssoclient[0].client_id
    assert decoded['sub'] == "ABC123"
    assert time.time() + 86390 < decoded['exp'] <= time.time() + 86400
    assert time.time() - 10 < decoded['iat'] <= time.time()
    assert time.time() - 10 < decoded['auth_time'] <= time.time()
    assert 'email' in decoded
    assert decoded['nonce'] == 'NONCE123'

    url = f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&' \
          f'redirect_uri=https://example.net&' \
          f'response_type=id_token+token&' \
          f'state=STATE&' \
          f'nonce=NONCE123&' \
          f'scope=openid+profile'
    r = client.get(url)
    assert r.status_code == 302
    match = re.match(r'https://example.net#access_token=([^&]+)&token_type=Bearer&'
                     r'expires_in=([^&]+)&id_token=([^&]+)&state=STATE', r.headers['Location'])
    assert match
    assert 86390 < int(match.group(2)) <= 86400
    decoded = jwt.decode(match.group(3), env[0].settings.sso_server_signing_key_rsa256_public, algorithms=["RS256"],
                         audience=ssoclient[0].client_id)
    assert decoded['at_hash'] == _hash_scheme(match.group(1))


@pytest.mark.django_db
def test_authorize_hybrid_flow(env, client, ssoclient):
    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 302

    url = f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&' \
          f'redirect_uri=https://example.net&' \
          f'response_type=code+id_token&' \
          f'state=STATE&' \
          f'nonce=NONCE123&' \
          f'scope=openid+profile'
    r = client.get(url)
    assert r.status_code == 302
    match = re.match(r'https://example.net#code=([^&]+)&id_token=([^&]+)&state=STATE', r.headers['Location'])
    assert match
    env[0].settings.flush()
    decoded = jwt.decode(match.group(2), env[0].settings.sso_server_signing_key_rsa256_public, algorithms=["RS256"],
                         audience=ssoclient[0].client_id)
    assert decoded['c_hash'] == _hash_scheme(match.group(1))

    url = f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&' \
          f'redirect_uri=https://example.net&' \
          f'response_type=code+id_token+token&' \
          f'state=STATE&' \
          f'nonce=NONCE123&' \
          f'scope=openid+profile'
    r = client.get(url)
    assert r.status_code == 302
    match = re.match(r'https://example.net#code=([^&]+)&access_token=([^&]+)&token_type=Bearer&'
                     r'expires_in=([^&]+)&id_token=([^&]+)&state=STATE', r.headers['Location'])
    assert match
    decoded = jwt.decode(match.group(4), env[0].settings.sso_server_signing_key_rsa256_public, algorithms=["RS256"],
                         audience=ssoclient[0].client_id)
    assert decoded['c_hash'] == _hash_scheme(match.group(1))
    assert decoded['at_hash'] == _hash_scheme(match.group(2))

    url = f'/bigevents/oauth2/v1/authorize?client_id={ssoclient[0].client_id}&' \
          f'redirect_uri=https://example.net&' \
          f'response_type=code+token&' \
          f'state=STATE&' \
          f'nonce=NONCE123&' \
          f'scope=openid+profile'
    r = client.get(url)
    assert r.status_code == 302
    match = re.match(r'https://example.net#code=([^&]+)&access_token=([^&]+)&token_type=Bearer&'
                     r'expires_in=([^&]+)&state=STATE', r.headers['Location'])
    assert match


def _acquire_token(client, ssoclient):
    code = _authorization_step(client, ssoclient)

    r = client.post('/bigevents/oauth2/v1/token', {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': 'https://example.net'
    }, HTTP_AUTHORIZATION='Basic ' + base64.b64encode(f'{ssoclient[0].client_id}:{ssoclient[1]}'.encode()).decode())
    assert r.status_code == 200
    d = json.loads(r.content)
    return d['access_token']


@pytest.mark.django_db
def test_userinfo_auth_and_claims(env, client, ssoclient):
    ssoclient[0].allowed_scopes = ['openid', 'profile', 'phone']
    ssoclient[0].save()

    r = client.get('/bigevents/oauth2/v1/userinfo')
    assert r.status_code == 401

    r = client.get('/bigevents/oauth2/v1/userinfo', HTTP_AUTHORIZATION='Basic foo')
    assert r.status_code == 400

    r = client.get('/bigevents/oauth2/v1/userinfo', HTTP_AUTHORIZATION='Bearer invalid')
    assert r.status_code == 401

    token = _acquire_token(client, ssoclient)

    r = client.get('/bigevents/oauth2/v1/userinfo', HTTP_AUTHORIZATION=f'Bearer {token}')
    assert r.status_code == 200

    r = client.post('/bigevents/oauth2/v1/userinfo', {'access_token': token})
    assert r.status_code == 200

    data = json.loads(r.content)
    assert data == {
        'sub': 'ABC123',
        'locale': 'en',
        'name': 'John Doe',
        'given_name': 'John',
        'family_name': 'Doe',
        'phone_number': '+49 30 2270'
    }


@pytest.mark.django_db
def test_config_endpoint(env, client, ssoclient):
    r = client.get('/bigevents/.well-known/openid-configuration')
    assert r.status_code == 200
    data = json.loads(r.content)
    assert data['issuer'] == 'http://example.com/bigevents'


@pytest.mark.django_db
def test_keys_endpoint(env, client, ssoclient):
    r = client.get('/bigevents/oauth2/v1/keys')
    assert r.status_code == 200
    data = json.loads(r.content)
    env[0].settings.flush()

    def decode_int(d: str):
        b = d.encode()
        padded = b + (b'=' * (-len(b) % 4))
        return int(hexlify(base64.urlsafe_b64decode(padded)), 16)

    e = decode_int(data['keys'][0]['e'])
    n = decode_int(data['keys'][0]['n'])
    pubkey = RSA.construct((n, e))
    representation = pubkey.export_key('PEM').decode()
    assert representation.strip() == env[0].settings.sso_server_signing_key_rsa256_public.strip()
