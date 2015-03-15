from django.dispatch import receiver

from pretix.base.signals import register_payment_providers

from .payment import Paypal


@receiver(register_payment_providers)
def register_payment_provider(sender, **kwargs):
    return Paypal
