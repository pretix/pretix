try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+


class PartnersMerchantIntegrationsGetRequest:
    """
    Retrieves the Merchant Account Status of a Partner Merchant Integration.
    """
    def __init__(self, partner_merchant_id, seller_merchant_id):
        self.verb = "GET"
        self.path = "/v1/customer/partners/{partner_merchant_id}/merchant-integrations/{seller_merchant_id}".format(
            partner_merchant_id=quote(str(partner_merchant_id)),
            seller_merchant_id=quote(str(seller_merchant_id))
        )
        self.headers = {}
        self.headers["Content-Type"] = "application/json"
        self.body = None

    def prefer(self, prefer):
        self.headers["Prefer"] = str(prefer)
