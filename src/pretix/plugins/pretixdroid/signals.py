
from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _

from pretix.base.signals import logentry_display
from pretix.control.logdisplay import _display_checkin
from pretix.control.signals import nav_event


@receiver(nav_event, dispatch_uid="pretixdroid_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(request.organizer, request.event, 'can_change_orders', request=request):
        return []
    return [
        {
            'label': _('Check-in devices'),
            'url': reverse('plugins:pretixdroid:config', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'parent': reverse('control:event.orders.checkinlists', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': (url.namespace == 'plugins:pretixdroid' and url.url_name == 'config'),
            'icon': 'mobile',
        }
    ]


@receiver(signal=logentry_display, dispatch_uid="pretixdroid_logentry_display")
def pretixcontrol_logentry_display(sender, logentry, **kwargs):
    if logentry.action_type != 'pretix.plugins.pretixdroid.scan':
        return

    return _display_checkin(sender, logentry)
