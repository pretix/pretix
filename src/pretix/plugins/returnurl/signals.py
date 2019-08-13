from django.core.exceptions import PermissionDenied
from django.dispatch import receiver
from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.utils.translation import ugettext_lazy as _

from pretix.control.signals import nav_event_settings
from pretix.presale.signals import process_request


@receiver(process_request, dispatch_uid="returnurl_process_request")
def returnurl_process_request(sender, request, **kwargs):
    try:
        r = resolve(request.path_info)
    except:
        return

    urlname = r.url_name
    urlkwargs = r.kwargs

    if urlname.startswith('event.order'):
        key = 'order_{}_{}_{}_return_url'.format(urlkwargs.get('organizer', '-'), urlkwargs['event'],
                                                 urlkwargs['order'])
        if urlname == 'event.order' and key in request.session:
            r = redirect(request.session.get(key))
            del request.session[key]
            return r
        elif urlname != 'event.order' and 'return_url' in request.GET:
            u = request.GET.get('return_url')
            if not sender.settings.returnurl_prefix:
                raise PermissionDenied('No return URL prefix set.')
            elif not u.startswith(sender.settings.returnurl_prefix):
                raise PermissionDenied('Invalid return URL.')
            request.session[key] = u


@receiver(nav_event_settings, dispatch_uid='returnurl_nav')
def navbar_info(sender, request, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(request.organizer, request.event, 'can_change_event_settings',
                                             request=request):
        return []
    return [{
        'label': _('Redirection'),
        'url': reverse('plugins:returnurl:settings', kwargs={
            'event': request.event.slug,
            'organizer': request.organizer.slug,
        }),
        'active': url.namespace == 'plugins:returnurl',
    }]
