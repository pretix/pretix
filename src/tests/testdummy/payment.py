import logging

from django.http import HttpRequest

from pretix.base.models import OrderPayment
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


class DummyFullRefundablePaymentProvider(BasePaymentProvider):
    identifier = 'testdummy_fullrefund'
    verbose_name = 'Test dummy'
    abort_pending_allowed = False

    def payment_is_valid_session(self, request: HttpRequest) -> bool:
        pass

    def checkout_confirm_render(self, request) -> str:
        pass

    def payment_refund_supported(self, payment: OrderPayment) -> bool:
        return True


class DummyPartialRefundablePaymentProvider(BasePaymentProvider):
    identifier = 'testdummy_partialrefund'
    verbose_name = 'Test dummy'
    abort_pending_allowed = False

    def payment_is_valid_session(self, request: HttpRequest) -> bool:
        pass

    def checkout_confirm_render(self, request) -> str:
        pass

    def payment_refund_supported(self, payment: OrderPayment) -> bool:
        return True

    def payment_partial_refund_supported(self, payment: OrderPayment) -> bool:
        return True
