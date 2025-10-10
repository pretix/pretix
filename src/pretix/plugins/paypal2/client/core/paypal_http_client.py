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
import copy
import hashlib
import logging
import uuid

import requests
from django.core.cache import cache
from paypalcheckoutsdk.core import (
    AccessToken, PayPalHttpClient as VendorPayPalHttpClient,
)
from requests.adapters import HTTPAdapter
from urllib3 import Retry
from urllib3.exceptions import MaxRetryError

logger = logging.getLogger(__name__)


class LogOnRetry(Retry):
    def increment(self, method=None, url=None, response=None, error=None, _pool=None, _stacktrace=None) -> Retry:
        logstr = f'({method} {url}): {error if error else (response.status if response else "unknown")}'
        logger.warning(f'PayPal2 Retry called {logstr} after {len(self.history)} attempts')
        try:
            return super().increment(method, url, response, error, _pool, _stacktrace)
        except MaxRetryError:
            logger.error(f'PayPal2 Retry failed {logstr} after {len(self.history)} attempts')
            raise


class PayPalHttpClient(VendorPayPalHttpClient):
    def __init__(self, environment):
        super().__init__(environment)

        self.session = requests.Session()
        retries = LogOnRetry(
            total=5,
            backoff_factor=0.05,
            # Yes, we retry on 404. Starting December 20th, we noticed high levels of inconsistency
            # with PayPal's system, where executing GET on the same order ID would only succeed
            # ~50% of the time, as if we were routed to inconsistent databases within PayPal.
            status_forcelist=[404, 500, 502, 503, 504],
            # We also need to add non-idempotent methods since OrdersPatchRequest and OrdersCaptureRequest
            # are also affected. Oof. Let's hope we're idempotent enough by setting PayPal-Request-Id.
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "PATCH", "POST"],
            raise_on_status=False,
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def __call__(self, request):
        # Cached access tokens are not updated by PayPal to include new Merchants that granted access rights since
        # the access token was generated. Therefor we increment the cycle count and by that invalidate the cached
        # token and pull a new one.
        incr = cache.get('pretix_paypal_token_hash_cycle', default=1)

        # Then we get all the items that make up the current credentials and create a hash to detect changes
        checksum = hashlib.sha256(''.join([
            self.environment.base_url, self.environment.client_id, self.environment.client_secret
        ]).encode()).hexdigest()
        cache_key_hash = f'pretix_paypal_token_hash_{checksum}_{incr}'
        token_hash = cache.get(cache_key_hash)

        if token_hash:
            # First we set an optional access token
            self._access_token = AccessToken(
                access_token=token_hash['access_token'],
                expires_in=token_hash['expires_in'],
                token_type=token_hash['token_type'],
            )
            # This is not part of the constructor - so we need to set it after the fact.
            self._access_token.created_at = token_hash['created_at']

        # Only then we'll call the original __call__() method, as it will verify the validity of the tokens
        # and request new ones if required.
        super().__call__(request)

        # At this point - if there were any changes in access-token, we should have them and can cache them again
        if self._access_token and (not token_hash or token_hash['access_token'] != self._access_token.access_token):
            expiration = self._access_token.expires_in - 60  # For good measure, we expire 60 seconds earlier

            cache.set(cache_key_hash, {
                'access_token': self._access_token.access_token,
                'expires_in': self._access_token.expires_in,
                'token_type': self._access_token.token_type,
                'created_at': self._access_token.created_at
            }, expiration)

        # And now for some housekeeping.
        if self.environment.merchant_id:
            request.headers["PayPal-Auth-Assertion"] = self.environment.authorization_assertation()

        if self.environment.partner_id:
            request.headers["PayPal-Partner-Attribution-Id"] = self.environment.partner_id

        if "PayPal-Request-Id" not in request.headers:
            request.headers["PayPal-Request-Id"] = str(uuid.uuid4())

    def execute(self, request):
        reqCpy = copy.deepcopy(request)

        try:
            getattr(reqCpy, 'headers')
        except AttributeError:
            reqCpy.headers = {}

        for injector in self._injectors:
            injector(reqCpy)

        data = None

        formatted_headers = self.format_headers(reqCpy.headers)

        if "user-agent" not in formatted_headers:
            reqCpy.headers["user-agent"] = self.get_user_agent()

        if hasattr(reqCpy, 'body') and reqCpy.body is not None:
            raw_headers = reqCpy.headers
            reqCpy.headers = formatted_headers
            data = self.encoder.serialize_request(reqCpy)
            reqCpy.headers = self.map_headers(raw_headers, formatted_headers)

        resp = self.session.request(
            method=reqCpy.verb,
            url=self.environment.base_url + reqCpy.path,
            headers=reqCpy.headers,
            data=data
        )

        return self.parse_response(resp)
