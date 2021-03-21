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
import logging

from django.http import HttpRequest

from pretix.base.models import OrderPayment, OrderRefund
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

    def execute_refund(self, refund: OrderRefund):
        refund.done()

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

    def execute_refund(self, refund: OrderRefund):
        refund.done()

    def payment_is_valid_session(self, request: HttpRequest) -> bool:
        pass

    def checkout_confirm_render(self, request) -> str:
        pass

    def payment_refund_supported(self, payment: OrderPayment) -> bool:
        return True

    def payment_partial_refund_supported(self, payment: OrderPayment) -> bool:
        return True
