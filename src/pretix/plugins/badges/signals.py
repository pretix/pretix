from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import ugettext_lazy as _

from pretix.control.signals import nav_event


@receiver(nav_event, dispatch_uid="badges_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    p = (
        request.user.has_event_permission(request.organizer, request.event, 'can_change_settings')
        or request.user.has_event_permission(request.organizer, request.event, 'can_view_orders')
    )
    if not p:
        return []
    return [
        {
            'label': _('Badges'),
            'url': reverse('plugins:badges:index', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': (url.namespace == 'plugins:badges' and url.url_name == 'index'),
            'icon': 'id-card',
        }
    ]
