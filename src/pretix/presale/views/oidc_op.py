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
import hashlib
import time
from binascii import unhexlify
from datetime import timedelta
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from Crypto.PublicKey import RSA
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_post_parameters

from pretix.base.customersso.oidc import (
    _get_or_create_server_keypair, customer_claims, generate_id_token,
)
from pretix.base.models.customers import (
    CustomerSSOAccessToken, CustomerSSOClient, CustomerSSOGrant,
)
from pretix.multidomain.middlewares import CsrfViewMiddleware
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.presale.forms.customer import AuthenticationForm
from pretix.presale.utils import customer_login, get_customer_auth_time

"""
We implement the OpenID Connect spec as per https://openid.net/specs/openid-connect-core-1_0.html
Based on the OAuth spec as per https://www.rfc-editor.org/rfc/rfc6749

We implement all three flows (authorization code, implicit, hybrid), as well as some typical standard
claims.

We currently do not implement the following optional parts of the spec:

- 4.  Initiating Login from a Third Party
- 5.5.  Requesting Claims using the "claims" Request Parameter
- 5.6.2.  Aggregated and Distributed Claims
- 6.  Passing Request Parameters as JWTs
- 8.1.  Pairwise Identifier Algorithm
- 9.  Client Authentication (except for client_secret_basic, client_secret_post)
- 10.2.  Encryption
- 11.  Offline Access
- 12.  Using Refresh Tokens

We also implement the Discovery extension (without issuer discovery)
as per https://openid.net/specs/openid-connect-discovery-1_0.html

The implementation passed the certification tests against the following profiles, but we did not
acquire formal certification:

- Basic OP
- Implicit OP
- Hybrid OP
- Config OP
"""

RESPONSE_TYPES_SUPPORTED = ("code", "id_token token", "id_token", "code id_token", "code id_token token", "code token")


class AuthorizeView(View):

    # We need to be exempt from CSRF because the spec mandates that relying parties can send requests as POST.
    # This is not a risk when we show a login form, because CSRF is pointless for a login form, if the attacker has
    # the password, they don't need to resort to CSRF. We still to a minimal validation below.
    # It would be a problem for a consent form, but we currently never show a consent form because it is not required
    # for our intended use case where all relying parties are at least somewhat trusted.
    @method_decorator(csrf_exempt)
    @method_decorator(never_cache)
    @method_decorator(sensitive_post_parameters())
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts or not request.organizer.settings.customer_accounts_native:
            raise Http404('Feature not enabled')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return self._process_auth_request(request, request.GET)

    def post(self, request, *args, **kwargs):
        try:
            CsrfViewMiddleware(lambda: None)._check_token(request)
        except:
            # External request, we prefer GET and will redirect to prevent confusion with our login form
            return redirect(request.path + '?' + request.POST.urlencode())
        return self._process_auth_request(request, request.GET)

    def _final_error(self, error, error_description):
        return HttpResponse(
            f'Error: {error_description} ({error})',
            status=400,
        )

    def _construct_redirect_uri(self, redirect_uri, response_mode, params):
        ru = urlparse(redirect_uri)
        qs = parse_qs(ru.query)
        fm = parse_qs(ru.fragment)
        if response_mode == 'query':
            qs.update(params)
        elif response_mode == 'fragment':
            fm.update(params)
        query = urlencode(qs, doseq=True)
        fragment = urlencode(fm, doseq=True)
        return urlunparse((ru.scheme, ru.netloc, ru.path, ru.params, query, fragment))

    def _redirect_error(self, error, error_description, redirect_uri, response_mode, state):
        qs = {'error': error, 'error_description': error_description}
        if state:
            qs['state'] = state
        return redirect(
            self._construct_redirect_uri(redirect_uri, response_mode, qs)
        )

    def _require_login(self, request, client, scope, redirect_uri, response_type, response_mode, state, nonce):
        form = AuthenticationForm(data=request.POST if "login-email" in request.POST else None, request=request,
                                  prefix="login")
        if "login-email" in request.POST and form.is_valid():
            customer_login(request, form.get_customer())
            return self._success(client, scope, redirect_uri, response_type, response_mode, state, nonce, form.get_customer())
        else:
            return render(request, 'pretixpresale/organizers/customer_login.html', {
                'providers': [],
                'form': form,
            })

    def _success(self, client, scope, redirect_uri, response_type, response_mode, state, nonce, customer):
        response_type = response_type.split(' ')
        qs = {}
        id_token_kwargs = {}

        if 'code' in response_type:
            grant = client.grants.create(
                customer=customer,
                scope=' '.join(scope),
                redirect_uri=redirect_uri,
                code=get_random_string(64),
                expires=now() + timedelta(minutes=10),
                auth_time=get_customer_auth_time(self.request),
                nonce=nonce,
            )
            qs['code'] = grant.code
            id_token_kwargs['with_code'] = grant.code

        expires = now() + timedelta(hours=24)

        if 'token' in response_type:
            token = client.access_tokens.create(
                customer=customer,
                token=get_random_string(128),
                expires=expires,
                scope=' '.join(scope),
            )
            qs['access_token'] = token.token
            qs['token_type'] = 'Bearer'
            qs['expires_in'] = int((token.expires - now()).total_seconds())
            id_token_kwargs['with_access_token'] = token.token

        if 'id_token' in response_type:
            qs['id_token'] = generate_id_token(
                customer,
                client,
                get_customer_auth_time(self.request),
                nonce,
                ' '.join(scope),
                expires,
                scope_claims='token' not in response_type and 'code' not in response_type,
                **id_token_kwargs,
            )

        if state:
            qs['state'] = state

        r = redirect(self._construct_redirect_uri(redirect_uri, response_mode, qs))
        r['Cache-Control'] = 'no-store'
        r['Pragma'] = 'no-cache'
        return r

    def _process_auth_request(self, request, request_data):
        response_mode = request_data.get("response_mode")
        client_id = request_data.get("client_id")
        state = request_data.get("state")
        nonce = request_data.get("nonce")
        max_age = request_data.get("max_age")
        prompt = request_data.get("prompt")
        response_type = request_data.get("response_type")
        scope = request_data.get("scope", "").split(" ")

        if not client_id:
            return self._final_error("invalid_request", "client_id missing")

        try:
            client = self.request.organizer.sso_clients.get(is_active=True, client_id=client_id)
        except CustomerSSOClient.DoesNotExist:
            return self._final_error("unauthorized_client", "invalid client_id")

        redirect_uri = request_data.get("redirect_uri")
        if not redirect_uri or not client.allow_redirect_uri(redirect_uri):
            return self._final_error("invalid_request_uri", "invalid redirect_uri")

        if response_type not in RESPONSE_TYPES_SUPPORTED:
            return self._final_error("unsupported_response_type", "response_type unsupported")

        if response_type != "code" and response_mode == "query":
            return self._final_error("invalid_request", "response_mode query must not be used with implicit or hybrid flow")
        elif not response_mode:
            response_mode = "query" if response_type == "code" else "fragment"
        elif response_mode not in ("query", "fragment"):
            return self._final_error("invalid_request", "invalid response_mode")

        if "request" in request_data:
            return self._redirect_error("request_not_supported", "request_not_supported", redirect_uri, response_mode, state)

        if response_type not in ("code", "code token") and not nonce:
            return self._redirect_error("invalid_request", "nonce is required in implicit or hybrid flow", redirect_uri,
                                        response_mode, state)

        if "openid" not in scope:
            return self._redirect_error("invalid_scope", "scope 'openid' must be requested", redirect_uri,
                                        response_mode, state)

        if "id_token_hint" in request_data:
            self._redirect_error("invalid_request", "id_token_hint currently not supported by this server",
                                 redirect_uri, response_mode, state)

        has_valid_session = bool(request.customer)
        if has_valid_session and max_age:
            try:
                has_valid_session = int(time.time() - get_customer_auth_time(request)) < int(max_age)
            except ValueError:
                self._redirect_error("invalid_request", "invalid max_age value", redirect_uri, response_mode, state)

        if not has_valid_session and prompt and prompt == "none":
            return self._redirect_error("interaction_required", "user is not logged in but no prompt is allowed",
                                        redirect_uri, response_mode, state)
        elif prompt in ("select_account", "login"):
            has_valid_session = False

        if has_valid_session:
            return self._success(client, scope, redirect_uri, response_type, response_mode, state, nonce, request.customer)
        else:
            return self._require_login(request, client, scope, redirect_uri, response_type, response_mode, state, nonce)


class TokenView(View):
    @method_decorator(csrf_exempt)
    @method_decorator(never_cache)
    @method_decorator(sensitive_post_parameters())
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts or not request.organizer.settings.customer_accounts_native:
            raise Http404('Feature not enabled')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if auth_header:
            encoded_credentials = auth_header.split(' ')[1]  # Removes "Basic " to isolate credentials
            decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8").split(':')
            client_id = decoded_credentials[0]
            client_secret = decoded_credentials[1]
            try:
                self.client = request.organizer.sso_clients.get(client_id=client_id, is_active=True)
            except CustomerSSOClient.DoesNotExist:
                return JsonResponse({
                    "error": "invalid_client",
                    "error_description": "Unknown or inactive client_id"
                }, status=401, headers={
                    'WWW-Authenticate': 'error="invalid_client"&error_description="Unknown or inactive client_id"'
                })
            if not self.client.check_client_secret(client_secret):
                return JsonResponse({
                    "error": "invalid_client",
                    "error_description": "Wrong client_secret"
                }, status=401, headers={
                    'WWW-Authenticate': 'error="invalid_client"&error_description="Wrong client_secret"'
                })
        elif request.POST.get("client_id"):
            try:
                self.client = request.organizer.sso_clients.get(client_id=request.POST["client_id"], is_active=True)
            except CustomerSSOClient.DoesNotExist:
                return JsonResponse({
                    "error": "invalid_client",
                    "error_description": "Unknown or inactive client_id"
                }, status=400)
            if "client_secret" in request.POST:
                if not self.client.check_client_secret(request.POST.get("client_secret")):
                    return JsonResponse({
                        "error": "invalid_client",
                        "error_description": "Wrong client_secret"
                    }, status=401, headers={
                        'WWW-Authenticate': 'error="invalid_client"&error_description="Wrong client_secret"'
                    })
            elif self.client.client_type != CustomerSSOClient.CLIENT_PUBLIC:
                return JsonResponse({
                    "error": "invalid_client",
                    "error_description": "Client is confidential, authentication required"
                }, status=400)
        else:
            return JsonResponse({
                "error": "invalid_client",
                "error_description": "Client is confidential, authentication required"
            }, status=400)

        grant_type = request.POST.get("grant_type")
        if grant_type == "authorization_code":
            return self._handle_authorization_code(request)
        else:
            return JsonResponse({
                "error": "unsupported_grant_type"
            }, status=400)

    def _handle_authorization_code(self, request):
        code = request.POST.get("code")
        redirect_uri = request.POST.get("redirect_uri")
        if not code:
            return JsonResponse({
                "error": "invalid_grant",
            }, status=400)

        try:
            grant = self.client.grants.get(code=code, expires__gt=now())
        except CustomerSSOGrant.DoesNotExist:
            # The server must return an invalid_grant error as the authorization code has already been used.
            # The originally issued access token should be revoked (as per RFC6749-4.1.2)
            CustomerSSOAccessToken.objects.filter(
                client=self.client,
                from_code=code
            ).update(expires=now() - timedelta(seconds=1))
            return JsonResponse({
                "error": "invalid_grant",
                "error_description": "Unknown or expired authorization code"
            }, status=400)

        if grant.redirect_uri != redirect_uri:
            return JsonResponse({
                "error": "invalid_grant",
                "error_description": "Mismatch of redirect_uri"
            }, status=400)

        with transaction.atomic():
            token = self.client.access_tokens.create(
                customer=grant.customer,
                token=get_random_string(128),
                expires=now() + timedelta(hours=24),
                scope=grant.scope,
                from_code=code,
            )
            grant.delete()

        return JsonResponse({
            "access_token": token.token,
            "token_type": "Bearer",
            "expires_in": int((token.expires - now()).total_seconds()),
            "id_token": generate_id_token(grant.customer, self.client, grant.auth_time, grant.nonce, grant.scope, token.expires)
        }, headers={
            'Cache-Control': 'no-store',
            'Pragma': 'no-cache',
        })


class UserInfoView(View):
    @method_decorator(csrf_exempt)
    @method_decorator(never_cache)
    @method_decorator(sensitive_post_parameters())
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts or not request.organizer.settings.customer_accounts_native:
            raise Http404('Feature not enabled')

        auth_header = request.headers.get('Authorization')
        if auth_header:
            method, token = auth_header.split(' ', 1)
            if method != 'Bearer':
                return JsonResponse({
                    "error": "invalid_request",
                    "error_description": "Unknown authorization method"
                }, status=400, headers={
                    'Access-Control-Allow-Origin': '*',
                })
        elif request.method == "POST" and "access_token" in request.POST:
            token = request.POST.get("access_token")
        else:
            return HttpResponse(status=401, headers={
                'WWW-Authenticate': 'Bearer realm="example"',
                'Access-Control-Allow-Origin': '*',
            })

        try:
            access_token = CustomerSSOAccessToken.objects.get(
                token=token, expires__gt=now(), client__organizer=self.request.organizer,
            )
        except CustomerSSOAccessToken.DoesNotExist:
            return JsonResponse({
                "error": "invalid_token",
                "error_description": "Unknown access token"
            }, status=401, headers={
                'WWW-Authenticate': 'error="invalid_token"&error_description="Unknown access token"',
                'Access-Control-Allow-Origin': '*',
            })
        else:
            self.customer = access_token.customer
            self.access_token = access_token

        r = super().dispatch(request, *args, **kwargs)
        r['Access-Control-Allow-Origin'] = '*'
        return r

    def post(self, request, *args, **kwargs):
        return self._handle(request)

    def get(self, request, *args, **kwargs):
        return self._handle(request)

    def _handle(self, request):
        return JsonResponse(customer_claims(self.customer, self.access_token.client.evaluated_scope(self.access_token.scope)))


class KeysView(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts or not request.organizer.settings.customer_accounts_native:
            raise Http404('Feature not enabled')
        r = super().dispatch(request, *args, **kwargs)
        r['Access-Control-Allow-Origin'] = '*'
        return r

    def _encode_int(self, i):
        hexi = hex(i)[2:]
        return base64.urlsafe_b64encode(unhexlify((len(hexi) % 2) * '0' + hexi))

    def get(self, request, *args, **kwargs):
        privkey, pubkey = _get_or_create_server_keypair(request.organizer)
        kid = hashlib.sha256(pubkey.encode()).hexdigest()[:16]
        pubkey = RSA.import_key(pubkey)

        return JsonResponse({
            'keys': [
                {
                    'kty': 'RSA',
                    'alg': 'RS256',
                    'kid': kid,
                    'use': 'sig',
                    'e': self._encode_int(pubkey.e).decode().rstrip("="),
                    'n': self._encode_int(pubkey.n).decode().rstrip("="),
                }
            ]
        })


class ConfigurationView(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts or not request.organizer.settings.customer_accounts_native:
            raise Http404('Feature not enabled')
        r = super().dispatch(request, *args, **kwargs)
        r['Access-Control-Allow-Origin'] = '*'
        return r

    def get(self, request, *args, **kwargs):
        return JsonResponse({
            'issuer': build_absolute_uri(request.organizer, 'presale:organizer.index').rstrip('/'),
            'authorization_endpoint': build_absolute_uri(
                request.organizer, 'presale:organizer.oauth2.v1.authorize'
            ),
            'token_endpoint': build_absolute_uri(
                request.organizer, 'presale:organizer.oauth2.v1.token'
            ),
            'userinfo_endpoint': build_absolute_uri(
                request.organizer, 'presale:organizer.oauth2.v1.userinfo'
            ),
            'jwks_uri': build_absolute_uri(
                request.organizer, 'presale:organizer.oauth2.v1.jwks'
            ),
            'scopes_supported': [k for k, v in CustomerSSOClient.SCOPE_CHOICES],
            'response_types_supported': RESPONSE_TYPES_SUPPORTED,
            'response_modes_supported': ['query', 'fragment'],
            'request_parameter_supported': False,
            'grant_types_supported': ['authorization_code', 'implicit'],
            'subject_types_supported': ['public'],
            'id_token_signing_alg_values_supported': ['RS256'],
            'token_endpoint_auth_methods_supported': [
                'client_secret_post', 'client_secret_basic'
            ],
            'claims_supported': [
                'iss',
                'aud',
                'exp',
                'iat',
                'auth_time',
                'nonce',
                'c_hash',
                'at_hash',
                'sub',
                'locale',
                'name',
                'given_name',
                'family_name',
                'middle_name',
                'nickname',
                'email',
                'email_verified',
                'phone_number',
            ],
            'request_uri_parameter_supported': False,

        })
