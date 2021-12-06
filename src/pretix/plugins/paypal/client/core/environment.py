import jwt

from paypalcheckoutsdk.core import PayPalEnvironment as VendorPayPalEnvironment


class PayPalEnvironment(VendorPayPalEnvironment):
    def __init__(self, client_id, client_secret, apiUrl, webUrl, merchant_id, partner_id):
        super(PayPalEnvironment, self).__init__(client_id, client_secret, apiUrl, webUrl)
        self.merchant_id = merchant_id
        self.partner_id = partner_id

    def authorization_assertation(self):
        if self.merchant_id:
            return jwt.encode(
                payload={
                    'iss': self.client_id,
                    'payer_id': self.merchant_id
                },
                key=None,
                algorithm=None,
            )
        return ""


class SandboxEnvironment(PayPalEnvironment):
    def __init__(self, client_id, client_secret, merchant_id=None, partner_id=None):
        super(SandboxEnvironment, self).__init__(
            client_id,
             client_secret,
             PayPalEnvironment.SANDBOX_API_URL,
             PayPalEnvironment.SANDBOX_WEB_URL,
             merchant_id,
             partner_id
        )


class LiveEnvironment(PayPalEnvironment):
    def __init__(self, client_id, client_secret, merchant_id, partner_id):
        super(LiveEnvironment, self).__init__(
            client_id,
            client_secret,
            PayPalEnvironment.LIVE_API_URL,
            PayPalEnvironment.LIVE_WEB_URL,
            merchant_id,
            partner_id
        )
