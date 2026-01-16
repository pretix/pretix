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
import base64
import hashlib
import logging
import time
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urljoin

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat,
)
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from requests import RequestException

from pretix.multidomain.urlreverse import build_absolute_uri

logger = logging.getLogger(__name__)


"""
This module contains utilities for implementing OpenID Connect for customer authentication both as a receiving party (RP)
as well as an OpenID Provider (OP).
"""

pretix_token_endpoint_auth_methods = ['client_secret_basic', 'client_secret_post']


def _urljoin(base, path):
    if not base.endswith("/"):
        base += "/"
    return urljoin(base, path)


def oidc_validate_and_complete_config(config):
    for k in ("base_url", "client_id", "client_secret", "uid_field", "email_field", "scope"):
        if not config.get(k):
            raise ValidationError(_('Configuration option "{name}" is missing.').format(name=k))

    conf_url = _urljoin(config["base_url"], ".well-known/openid-configuration")
    try:
        resp = requests.get(conf_url, timeout=10)
        resp.raise_for_status()
        provider_config = resp.json()
    except RequestException as e:
        raise ValidationError(_('Unable to retrieve configuration from "{url}". Error message: "{error}".').format(
            url=conf_url,
            error=str(e)
        ))
    except ValueError as e:
        raise ValidationError(_('Unable to retrieve configuration from "{url}". Error message: "{error}".').format(
            url=conf_url,
            error=str(e)
        ))

    if not provider_config.get("authorization_endpoint"):
        raise ValidationError(_('Incompatible SSO provider: "{error}".').format(
            error="authorization_endpoint not set"
        ))

    if not provider_config.get("userinfo_endpoint"):
        raise ValidationError(_('Incompatible SSO provider: "{error}".').format(
            error="userinfo_endpoint not set"
        ))

    if not provider_config.get("token_endpoint"):
        raise ValidationError(_('Incompatible SSO provider: "{error}".').format(
            error="token_endpoint not set"
        ))

    if "code" not in provider_config.get("response_types_supported", []):
        raise ValidationError(_('Incompatible SSO provider: "{error}".').format(
            error=f"provider supports response types {','.join(provider_config.get('response_types_supported', []))}, but we only support 'code'."
        ))

    if "query" not in provider_config.get("response_modes_supported", ["query", "fragment"]):
        raise ValidationError(_('Incompatible SSO provider: "{error}".').format(
            error=f"provider supports response modes {','.join(provider_config.get('response_modes_supported', []))}, but we only support 'query'."
        ))

    if "authorization_code" not in provider_config.get("grant_types_supported", ["authorization_code", "implicit"]):
        raise ValidationError(_('Incompatible SSO provider: "{error}".').format(
            error=f"provider supports grant types {','.join(provider_config.get('grant_types_supported', ''))}, but we only support 'authorization_code'."
        ))

    if "openid" not in config["scope"].split(" "):
        raise ValidationError(
            _('You are not requesting "{scope}".').format(
                scope="openid",
            ))

    if "token_endpoint_auth_methods_supported" in provider_config:
        token_endpoint_auth_methods_supported = provider_config.get("token_endpoint_auth_methods_supported",
                                                                    ["client_secret_basic"])
        if not any(x in pretix_token_endpoint_auth_methods for x in token_endpoint_auth_methods_supported):
            raise ValidationError(
                _(f'No supported Token Endpoint Auth Methods supported: {token_endpoint_auth_methods_supported}').format(
                    token_endpoint_auth_methods_supported=", ".join(token_endpoint_auth_methods_supported)
                )
            )

    if "query_parameters" in config and config["query_parameters"]:
        config["query_parameters"] = urlencode(
            parse_qsl(config["query_parameters"])
        )

    config['provider_config'] = provider_config
    return config


def oidc_authorize_url(provider, state, redirect_uri, pkce_code_verifier):
    endpoint = provider.configuration['provider_config']['authorization_endpoint']
    params = {
        # https://datatracker.ietf.org/doc/html/rfc6749#section-4.1.1
        # https://openid.net/specs/openid-connect-core-1_0.html#AuthorizationEndpoint
        'response_type': 'code',
        'client_id': provider.configuration['client_id'],
        'scope': provider.configuration['scope'],
        'state': state,
        'redirect_uri': redirect_uri,
    }

    if "query_parameters" in provider.configuration and provider.configuration["query_parameters"]:
        params.update(parse_qsl(provider.configuration["query_parameters"]))

    if pkce_code_verifier and "S256" in provider.configuration['provider_config'].get('code_challenge_methods_supported', []):
        params["code_challenge"] = base64.urlsafe_b64encode(hashlib.sha256(pkce_code_verifier.encode()).digest()).decode().rstrip("=")
        params["code_challenge_method"] = "S256"

    return endpoint + '?' + urlencode(params)


def oidc_validate_authorization(provider, code, redirect_uri, pkce_code_verifier):
    endpoint = provider.configuration['provider_config']['token_endpoint']

    # Wall of shame and RFC ignorant IDPs
    if endpoint == 'https://www.linkedin.com/oauth/v2/accessToken':
        token_endpoint_auth_method = 'client_secret_post'
    else:
        token_endpoint_auth_methods = provider.configuration['provider_config'].get(
            'token_endpoint_auth_methods_supported', ['client_secret_basic']
        )
        token_endpoint_auth_method = [
            x for x in pretix_token_endpoint_auth_methods if x in token_endpoint_auth_methods
        ][0]

    params = {
        # https://datatracker.ietf.org/doc/html/rfc6749#section-4.1.3
        # https://openid.net/specs/openid-connect-core-1_0.html#TokenEndpoint
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
    }

    if pkce_code_verifier and "S256" in provider.configuration['provider_config'].get('code_challenge_methods_supported', []):
        params["code_verifier"] = pkce_code_verifier

    if token_endpoint_auth_method == 'client_secret_post':
        params['client_id'] = provider.configuration['client_id']
        params['client_secret'] = provider.configuration['client_secret']

    resp = None
    try:
        resp = requests.post(
            endpoint,
            data=params,
            headers={
                'Accept': 'application/json',
            },
            auth=(
                provider.configuration['client_id'],
                provider.configuration['client_secret']
            ) if token_endpoint_auth_method == 'client_secret_basic' else None,
        )
        resp.raise_for_status()
        data = resp.json()
    except RequestException:
        if resp:
            logger.exception(f'Could not retrieve authorization token. Response: {resp.text}')
        else:
            logger.exception('Could not retrieve authorization token')
        raise ValidationError(
            _('Login was not successful. Error message: "{error}".').format(
                error='could not reach login provider',
            )
        )

    if 'access_token' not in data:
        logger.error(f'Could not find access token. Response: {data}')
        raise ValidationError(
            _('Login was not successful. Error message: "{error}".').format(
                error='access token missing',
            )
        )

    endpoint = provider.configuration['provider_config']['userinfo_endpoint']
    resp = None
    try:
        # https://openid.net/specs/openid-connect-core-1_0.html#UserInfo
        resp = requests.get(
            endpoint,
            headers={
                'Authorization': f'Bearer {data["access_token"]}'
            },
        )
        resp.raise_for_status()
        userinfo = resp.json()
    except RequestException:
        if resp:
            logger.exception(f'Could not retrieve user info. Response: {resp.text}')
        else:
            logger.exception('Could not retrieve user info')
        raise ValidationError(
            _('Login was not successful. Error message: "{error}".').format(
                error='could not fetch user info',
            )
        )

    if 'email_verified' in userinfo and not userinfo['email_verified']:
        # todo: how universal is this, do we need to make this configurable?
        raise ValidationError(_('The email address on this account is not yet verified. Please first confirm the '
                                'email address in your customer account.'))

    profile = {}
    for k, v in provider.configuration.items():
        if k.endswith('_field'):
            profile[k[:-6]] = userinfo.get(v)

    if not profile.get('uid'):
        raise ValidationError(
            _('Login was not successful. Error message: "{error}".').format(
                error='could not fetch user id',
            )
        )

    if not profile.get('email'):
        raise ValidationError(
            _('Login was not successful. Error message: "{error}".').format(
                error='could not fetch user email',
            )
        )

    return profile


def _hash_scheme(value):
    # As described in https://openid.net/specs/openid-connect-core-1_0.html#HybridIDToken
    digest = hashlib.sha256(value.encode()).digest()
    digest_truncated = digest[:(len(digest) // 2)]
    return base64.urlsafe_b64encode(digest_truncated).decode().rstrip("=")


def customer_claims(customer, scope):
    scope = scope.split(' ')
    claims = {
        'sub': customer.identifier,
        'locale': customer.locale,
    }
    if 'profile' in scope:
        if customer.name:
            claims['name'] = customer.name
        if 'given_name' in customer.name_parts:
            claims['given_name'] = customer.name_parts['given_name']
        if 'family_name' in customer.name_parts:
            claims['family_name'] = customer.name_parts['family_name']
        if 'middle_name' in customer.name_parts:
            claims['middle_name'] = customer.name_parts['middle_name']
        if 'calling_name' in customer.name_parts:
            claims['nickname'] = customer.name_parts['calling_name']
    if 'email' in scope and customer.email:
        claims['email'] = customer.email
        claims['email_verified'] = customer.is_verified
    if 'phone' in scope and customer.phone:
        claims['phone_number'] = customer.phone.as_international
    return claims


def _get_or_create_server_keypair(organizer):
    if not organizer.settings.sso_server_signing_key_rsa256_private:
        privkey = generate_private_key(key_size=4096, public_exponent=65537)
        pubkey = privkey.public_key()
        organizer.settings.sso_server_signing_key_rsa256_private = privkey.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        ).decode()
        organizer.settings.sso_server_signing_key_rsa256_public = pubkey.public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        ).decode()
    return organizer.settings.sso_server_signing_key_rsa256_private, organizer.settings.sso_server_signing_key_rsa256_public


def generate_id_token(customer, client, auth_time, nonce, scope, expires: datetime, scope_claims=False, with_code=None, with_access_token=None):
    payload = {
        'iss': build_absolute_uri(client.organizer, 'presale:organizer.index').rstrip('/'),
        'aud': client.client_id,
        'exp': int(expires.timestamp()),
        'iat': int(time.time()),
        'auth_time': auth_time,
        **customer_claims(customer, client.evaluated_scope(scope) if scope_claims else ''),
    }
    if nonce:
        payload['nonce'] = nonce
    if with_code:
        payload['c_hash'] = _hash_scheme(with_code)
    if with_access_token:
        payload['at_hash'] = _hash_scheme(with_access_token)
    privkey, pubkey = _get_or_create_server_keypair(client.organizer)
    return jwt.encode(
        payload,
        privkey,
        headers={
            "kid": hashlib.sha256(pubkey.encode()).hexdigest()[:16]
        },
        algorithm="RS256",
    )
