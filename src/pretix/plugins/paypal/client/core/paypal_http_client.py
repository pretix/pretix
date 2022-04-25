import hashlib

from paypalcheckoutsdk.core import PayPalHttpClient as VendorPayPalHttpClient, AccessToken

from django.core.cache import cache


class PayPalHttpClient(VendorPayPalHttpClient):
    def __call__(self, request):
        # First we get all the items that make up the current credentials and create a hash to detect changes

        checksum = hashlib.sha256(''.join([
            self.environment.base_url, self.environment.client_id, self.environment.client_secret
        ]).encode()).hexdigest()
        cache_key_hash = f'pretix_paypal_token_hash_{checksum}'
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
