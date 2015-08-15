from django.core.urlresolvers import resolve, reverse
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

from pretix.base.signals import register_payment_providers
from pretix.control.signals import nav_event

from .payment import BankTransfer


@receiver(register_payment_providers, dispatch_uid="payment_banktransfer")
def register_payment_provider(sender, **kwargs):
    return BankTransfer


@receiver(nav_event, dispatch_uid="payment_banktransfer_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.eventperm.can_change_orders:
        return []
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
