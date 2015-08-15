from django.core.urlresolvers import resolve, reverse
from django.dispatch import receiver
from django.template import Context
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _

from pretix.control.signals import nav_event, html_head


@receiver(nav_event)
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.eventperm.can_view_orders:
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


@receiver(html_head)
def html_head_presale(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if url.namespace == 'plugins:statistics':
        template = get_template('pretixplugins/statistics/control_head.html')
        ctx = Context({})
        return template.render(ctx)
    else:
        return ""
