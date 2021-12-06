from paypalcheckoutsdk.core import PayPalHttpClient as VendorPayPalHttpClient, AccessTokenRequest, RefreshTokenRequest


class PayPalHttpClient(VendorPayPalHttpClient):
    def __call__(self, request):
        super().__call__(request)
        if "Authorization" not in request.headers and not isinstance(request, AccessTokenRequest) and not isinstance(request, RefreshTokenRequest):
            if self.environment.merchant_id:
                request.headers["PayPal-Auth-Assertion"] = self.environment.authorization_assertation()

            if self.environment.partner_id:
                request.headers["PayPal-Partner-Attribution-Id"] = self.environment.partner_id

