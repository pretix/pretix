from django.core.urlresolvers import resolve, reverse
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

from pretix.base.signals import order_paid, order_placed
from pretix.control.signals import nav_event


@receiver(nav_event, dispatch_uid="statistics_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(request.organizer, request.event, 'can_view_orders'):
        return []
    return [
        {
            'label': _('Statistics'),
            'url': reverse('plugins:statistics:index', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': (url.namespace == 'plugins:statistics'),
            'icon': 'bar-chart',
        }
    ]


def clear_cache(sender, *args, **kwargs):
    cache = sender.cache
    cache.delete('statistics_obd_data')
    cache.delete('statistics_obp_data')
    cache.delete('statistics_rev_data')


order_placed.connect(clear_cache)
order_paid.connect(clear_cache)
