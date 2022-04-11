from paypalcheckoutsdk.core import PayPalHttpClient as VendorPayPalHttpClient, AccessToken

from django.core.cache import cache


class PayPalHttpClient(VendorPayPalHttpClient):
    def __call__(self, request):
        # First we set an optional existing refresh and access token
        self._refresh_token = cache.get("pretix_paypal_refresh_token", None)

        access_token = cache.get("pretix_paypal_access_token", None)

        if access_token:
            self._access_token = AccessToken(
                access_token=cache.get("pretix_paypal_access_token"),
                expires_in=cache.get("pretix_paypal_access_token_expires_in"),
                token_type=cache.get("pretix_paypal_access_token_type"),
            )
            # This is not part of the constructor - so we need to set it after the fact.
            self._access_token.created_at = cache.get("pretix_paypal_access_token_created_at"),

        # Only then we'll call the original __call__() method, as it will verify the validity of the tokens
        # and request new ones if required.
        super().__call__(request)

        # At this point - if there were any changes in refresh or access-token, we should have them
        # and can cache them again
        if self._refresh_token:
            cache.set("pretix_paypal_refresh_token", self._refresh_token)

        if self._access_token and (not access_token or access_token != self._access_token.access_token):
            expiration = self._access_token.expires_in - 60  # For good measure, we expire 60 seconds earlier

            cache.set("pretix_paypal_access_token", self._access_token.access_token, expiration)
            cache.set("pretix_paypal_access_token_expires_in", self._access_token.expires_in, expiration)
            cache.set("pretix_paypal_access_token_type", self._access_token.token_type, expiration)
            cache.set("pretix_paypal_access_token_created_at", self._access_token.created_at, expiration)

        # And now for some housekeeping.
        if self.environment.merchant_id:
            request.headers["PayPal-Auth-Assertion"] = self.environment.authorization_assertation()

        if self.environment.partner_id:
            request.headers["PayPal-Partner-Attribution-Id"] = self.environment.partner_id
