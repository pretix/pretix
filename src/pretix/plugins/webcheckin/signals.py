from django.dispatch import receiver
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from pretix.control.signals import nav_event


@receiver(nav_event, dispatch_uid='webcheckin_nav_event')
def navbar_entry(sender, request, **kwargs):
    url = request.resolver_match
    if not request.user.has_event_permission(request.organizer, request.event, ('can_change_orders', 'can_checkin_orders'), request=request):
        return []
    return [{
        'label': mark_safe(_('Web Check-in') + ' <span class="label label-success">beta</span>'),
        'url': reverse('plugins:webcheckin:index', kwargs={
            'event': request.event.slug,
            'organizer': request.organizer.slug,
        }),
        'parent': reverse('control:event.orders.checkinlists', kwargs={
            'event': request.event.slug,
            'organizer': request.event.organizer.slug,
        }),
        'external': True,
        'icon': 'check-square-o',
        'active': url.namespace == 'plugins:webcheckin' and url.url_name.startswith('index'),
    }]
