from django.core.urlresolvers import reverse, resolve
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

from pretix.base.signals import register_payment_providers

from .payment import BankTransfer
from pretix.control.signals import nav_event


@receiver(register_payment_providers)
def register_payment_provider(sender, **kwargs):
    return BankTransfer


@receiver(nav_event)
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    return [
        {
            'label': _('Import bank data'),
            'url': reverse('plugins:banktransfer:import', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': (url.namespace == 'plugins:banktransfer' and url.url_name == 'import'),
            'icon': 'upload',
        }
    ]
