from django.dispatch import receiver

from pretix.base.signals import determine_availability


@receiver(determine_availability)
def availability_handler(sender, **kwargs):
    kwargs['sender'] = sender
    if sender.settings.testdummy_available is not None:
        variations = kwargs['variations']
        variations = [d.copy() for d in variations]
        for v in variations:
            v['available'] = (sender.settings.testdummy_available == 'yes')
        return variations
    return []
