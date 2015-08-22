from django.core.urlresolvers import resolve, reverse
from django.dispatch import receiver
from django.template import Context
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _

from pretix.control.signals import html_head, nav_event


@receiver(nav_event, dispatch_uid="pretixdroid_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.eventperm.can_change_orders:
        return []
    return [
        {
            'label': _('pretixdroid'),
            'url': reverse('plugins:pretixdroid:config', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': (url.namespace == 'plugins:pretixdroid' and url.url_name == 'config'),
            'icon': 'android',
        }
    ]


@receiver(html_head, dispatch_uid="pretixdroid_html_head")
def html_head_presale(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if url.namespace == 'plugins:pretixdroid':
        template = get_template('pretixplugins/pretixdroid/control_head.html')
        ctx = Context({})
        return template.render(ctx)
    else:
        return ""
