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
from django.dispatch import receiver

from pretix.base.channels import SalesChannel
from pretix.base.signals import (
    register_payment_providers, register_sales_channels,
    register_ticket_outputs,
)


@receiver(register_ticket_outputs, dispatch_uid="output_dummy")
def register_ticket_outputs(sender, **kwargs):
    from .ticketoutput import DummyTicketOutput
    return DummyTicketOutput


@receiver(register_payment_providers, dispatch_uid="payment_dummy")
def register_payment_provider(sender, **kwargs):
    from .payment import (
        DummyFullRefundablePaymentProvider,
        DummyPartialRefundablePaymentProvider, DummyPaymentProvider,
    )
    return [DummyPaymentProvider, DummyFullRefundablePaymentProvider, DummyPartialRefundablePaymentProvider]


class FoobazSalesChannel(SalesChannel):
    identifier = "baz"
    verbose_name = "Foobar"
    icon = "home"
    testmode_supported = False


class FoobarSalesChannel(SalesChannel):
    identifier = "bar"
    verbose_name = "Foobar"
    icon = "home"
    testmode_supported = True
    unlimited_items_per_order = True


@receiver(register_sales_channels, dispatch_uid="sc_dummy")
def register_sc(sender, **kwargs):
    return [FoobarSalesChannel, FoobazSalesChannel]
