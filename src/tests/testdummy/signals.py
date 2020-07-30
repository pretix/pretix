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
