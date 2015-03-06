from django.dispatch import receiver

from pretix.base.signals import register_payment_providers

from .payment import Stripe


@receiver(register_payment_providers)
def register_payment_provider(sender, **kwargs):
    return Stripe
