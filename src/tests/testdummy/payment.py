import logging

from django.http import HttpRequest

from pretix.base.payment import BasePaymentProvider

logger = logging.getLogger('tests.testdummy.ticketoutput')


class DummyPaymentProvider(BasePaymentProvider):
    identifier = 'testdummy'
    verbose_name = 'Test dummy'
    abort_pending_allowed = False

    def payment_is_valid_session(self, request: HttpRequest) -> bool:
        pass

    def checkout_confirm_render(self, request) -> str:
        pass
