from django.core.urlresolvers import reverse, resolve
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

from pretix.control.signals import nav_event


@receiver(nav_event)
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.eventperm.can_change_orders:
        return []
    return [
        {
            'label': _('Send out emails'),
            'url': reverse('plugins:sendmail:send', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': (url.namespace == 'plugins:sendmail' and url.url_name == 'send'),
            'icon': 'envelope',
        }
    ]
