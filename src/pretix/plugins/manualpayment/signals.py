from django.dispatch import receiver

from pretix.base.signals import register_payment_providers

from .payment import ManualPayment


@receiver(register_payment_providers, dispatch_uid="payment_manual")
def register_payment_provider(sender, **kwargs):
    return ManualPayment
