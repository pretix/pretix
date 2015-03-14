.. highlight:: python
   :linenothreshold: 5

Writing a payment provider plugin
=================================

In this document, we will walk through the creation of a payment provider plugin.

Please read :ref:`Creating a plugin <pluginsetup>` first, if you haven't already.

The signal
----------

The payment provider API does not make a lot of usage from signals, however, it
does use a signal to get a list of all available payment providers. Your plugin
should listen for this signal and return the subclass of ``pretix.base.payment.PaymentProvider``
that we'll soon create::

    from django.dispatch import receiver

    from pretix.base.signals import register_payment_providers

    from .payment import BankTransfer


    @receiver(register_payment_providers)
    def register_payment_provider(sender, **kwargs):
        return BankTransfer
