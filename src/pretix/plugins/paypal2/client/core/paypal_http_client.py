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
import hashlib

from django.core.cache import cache
from paypalcheckoutsdk.core import (
    AccessToken, PayPalHttpClient as VendorPayPalHttpClient,
)


class PayPalHttpClient(VendorPayPalHttpClient):
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
