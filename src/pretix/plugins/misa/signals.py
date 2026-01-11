from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.signals import order_paid
from pretix.control.signals import nav_event_settings
from .tasks import create_misa_invoice

@receiver(nav_event_settings, dispatch_uid='misa_nav')
def navbar_info(sender, request, **kwargs):
    url = request.resolver_match.url_name
    return [{
        'label': _('MISA E-Invoice'),
        'url': reverse('plugins:misa:settings', kwargs={
            'event': request.event.slug,
            'organizer': request.event.organizer.slug,
        }),
        'active': url.startswith('settings'),
    }]

@receiver(order_paid, dispatch_uid="misa_order_paid")
def order_paid_receiver(sender, order, **kwargs):
    if order.event.settings.misa_enabled:
        create_misa_invoice.apply_async(args=[order.pk])
