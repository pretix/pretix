try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+


class PartnerReferralCreateRequest:
    """
    Creates an Partner Referral.
    """
    def __init__(self):
        self.verb = "POST"
        self.path = "/v2/customer/partner-referrals?"
        self.headers = {}
        self.headers["Content-Type"] = "application/json"
        self.body = None

    def prefer(self, prefer):
        self.headers["Prefer"] = str(prefer)



    def request_body(self, order):
        self.body = order
        return self
