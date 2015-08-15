from django.core.urlresolvers import resolve, reverse
from django.dispatch import receiver
from django.template import Context
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _

from pretix.base.signals import order_paid, order_placed
from pretix.control.signals import html_head, nav_event


@receiver(nav_event, dispatch_uid="statistics_nav")
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


@receiver(html_head, dispatch_uid="statistics_html_head")
def html_head_presale(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if url.namespace == 'plugins:statistics':
        template = get_template('pretixplugins/statistics/control_head.html')
        ctx = Context({})
        return template.render(ctx)
    else:
        return ""


def clear_cache(sender, *args, **kwargs):
    cache = sender.get_cache()
    cache.delete('statistics_obd_data')
    cache.delete('statistics_obp_data')
    cache.delete('statistics_rev_data')


order_placed.connect(clear_cache)
order_paid.connect(clear_cache)
