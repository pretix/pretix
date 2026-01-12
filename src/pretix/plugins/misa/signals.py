from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.signals import order_paid
from pretix.control.signals import nav_event, nav_event_settings
from .tasks import create_misa_invoice

@receiver(nav_event_settings, dispatch_uid='misa_nav_settings')
def navbar_settings(sender, request, **kwargs):
    url = request.resolver_match.url_name
    return [{
        'label': _('MISA E-Invoice'),
        'url': reverse('plugins:misa:settings', kwargs={
            'event': request.event.slug,
            'organizer': request.event.organizer.slug,
        }),
        'active': url == 'settings' and 'misa' in request.resolver_match.namespaces,
    }]

@receiver(nav_event, dispatch_uid='misa_nav_history')
def navbar_history(sender, request, **kwargs):
    url = request.resolver_match.url_name
    return [{
        'label': _('MISA History'),
        'url': reverse('plugins:misa:history', kwargs={
            'event': request.event.slug,
            'organizer': request.event.organizer.slug,
        }),
        'active': url == 'history' and 'misa' in request.resolver_match.namespaces,
        'icon': 'file-text-o',
    }]

@receiver(order_paid, dispatch_uid="misa_order_paid")
def order_paid_receiver(sender, order, **kwargs):
    if order.event.settings.misa_enabled:
        create_misa_invoice.apply_async(args=[order.pk])
