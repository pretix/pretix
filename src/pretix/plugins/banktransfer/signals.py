from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _

from pretix.base.signals import register_payment_providers
from pretix.control.signals import html_head, nav_event, nav_organizer

from .payment import BankTransfer


@receiver(register_payment_providers, dispatch_uid="payment_banktransfer")
def register_payment_provider(sender, **kwargs):
    return BankTransfer


@receiver(nav_event, dispatch_uid="payment_banktransfer_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(request.organizer, request.event, 'can_change_orders', request=request):
        return []
    return [
        {
            'label': _("Bank transfer"),
            'url': reverse('plugins:banktransfer:import', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'icon': 'university fa-spin',
            'children': [
                {
                    'label': _('Import bank data'),
                    'url': reverse('plugins:banktransfer:import', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': (url.namespace == 'plugins:banktransfer' and url.url_name == 'import'),
                },
                {
                    'label': _('Export refunds'),
                    'url': reverse('plugins:banktransfer:refunds.list', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': (url.namespace == 'plugins:banktransfer' and url.url_name == 'refunds'),
                },
            ]
        },
    ]


@receiver(nav_organizer, dispatch_uid="payment_banktransfer_organav")
def control_nav_orga_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_organizer_permission(request.organizer, 'can_change_orders', request=request):
        return []
    if not request.organizer.events.filter(plugins__icontains='pretix.plugins.banktransfer'):
        return []
    return [
        {
            'label': _('Import bank data'),
            'url': reverse('plugins:banktransfer:import', kwargs={
                'organizer': request.organizer.slug,
            }),
            'active': (url.namespace == 'plugins:banktransfer' and url.url_name == 'import'),
            'icon': 'upload',
        }
    ]


@receiver(html_head, dispatch_uid="banktransfer_html_head")
def html_head_presale(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if url.namespace == 'plugins:banktransfer':
        template = get_template('pretixplugins/banktransfer/control_head.html')
        return template.render({})
    else:
        return ""
