import logging

from pretix.base.payment import BasePaymentProvider

logger = logging.getLogger('tests.testdummy.ticketoutput')


class DummyPaymentProvider(BasePaymentProvider):
    identifier = 'testdummy'
    verbose_name = 'Test dummy'

    def order_pending_render(self, request, order) -> str:
        pass

    def payment_is_valid_session(self, request) -> bool:
        pass

    def checkout_confirm_render(self, request) -> str:
        pass
