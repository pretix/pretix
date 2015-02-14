from django.dispatch import receiver

from pretix.base.signals import determine_availability


@receiver(determine_availability)
def availability_handler(sender, **kwargs):
    kwargs['sender'] = sender
    return kwargs
