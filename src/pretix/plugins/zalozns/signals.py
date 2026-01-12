from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.template.loader import get_template
from pretix.base.signals import order_paid
from pretix.control.signals import nav_event_settings, order_info
from .tasks import send_zns

@receiver(nav_event_settings, dispatch_uid='zalozns_nav')
def navbar_info(sender, request, **kwargs):
    url = request.resolver_match.url_name
    return [{
        'label': _('Zalo ZNS'),
        'url': reverse('plugins:zalozns:settings', kwargs={
            'event': request.event.slug,
            'organizer': request.event.organizer.slug,
        }),
        'active': url == 'settings' and 'zalozns' in request.resolver_match.namespaces,
    }]

@receiver(order_info, dispatch_uid="zalozns_order_info")
def order_info_receiver(sender, request, order, **kwargs):
    if not request.event.settings.zalozns_enabled:
        return ""
    template = get_template('pretixplugins/zalozns/order_info.html')
    ctx = {
        'order': order,
        'request': request,
    }
    return template.render(ctx)

@receiver(order_paid, dispatch_uid="zalozns_order_paid")
def order_paid_receiver(sender, order, **kwargs):
    if order.event.settings.zalozns_enabled:
        send_zns.apply_async(args=[order.pk])
