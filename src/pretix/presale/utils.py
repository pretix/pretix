import warnings
from importlib import import_module
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect
from django.urls import resolve
from django.utils.translation import ugettext_lazy as _

from pretix.base.middleware import LocaleMiddleware
from pretix.base.models import Event, Organizer
from pretix.multidomain.urlreverse import get_domain
from pretix.presale.signals import process_request, process_response

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore


def _detect_event(request, require_live=True, require_plugin=None):
    if hasattr(request, '_event_detected'):
        return

    url = resolve(request.path_info)
    try:
        if hasattr(request, 'organizer_domain'):
            # We are on an organizer's custom domain
            if 'organizer' in url.kwargs and url.kwargs['organizer']:
                if url.kwargs['organizer'] != request.organizer.slug:
                    raise Http404(_('The selected event was not found.'))
                path = "/" + request.get_full_path().split("/", 2)[-1]
                return redirect(path)

            request.event = request.organizer.events\
                .get(
                    slug=url.kwargs['event'],
                    organizer=request.organizer,
                )
            request.organizer = request.organizer
        else:
            # We are on our main domain
            if 'event' in url.kwargs and 'organizer' in url.kwargs:
                request.event = Event.objects\
                    .select_related('organizer')\
                    .get(
                        slug=url.kwargs['event'],
                        organizer__slug=url.kwargs['organizer']
                    )
                request.organizer = request.event.organizer
            elif 'organizer' in url.kwargs:
                request.organizer = Organizer.objects.get(
                    slug=url.kwargs['organizer']
                )
            else:
                raise Http404()

            # If this organizer has a custom domain, send the user there
            domain = get_domain(request.organizer)
            if domain:
                if request.port and request.port not in (80, 443):
                    domain = '%s:%d' % (domain, request.port)
                path = request.get_full_path().split("/", 2)[-1]
                return redirect(urljoin('%s://%s' % (request.scheme, domain), path))

        if hasattr(request, 'event'):
            # Restrict locales to the ones available for this event
            LocaleMiddleware().process_request(request)

            if require_live and not request.event.live:
                can_access = (
                    url.url_name == 'event.auth'
                    or (
                        request.user.is_authenticated
                        and request.user.has_event_permission(request.organizer, request.event, request=request)
                    )

                )
                if not can_access and 'pretix_event_access_{}'.format(request.event.pk) in request.session:
                    sparent = SessionStore(request.session.get('pretix_event_access_{}'.format(request.event.pk)))
                    try:
                        parentdata = sparent.load()
                    except:
                        pass
                    else:
                        can_access = 'event_access' in parentdata

                if not can_access:
                    raise PermissionDenied(_('The selected ticket shop is currently not available.'))

            if require_plugin:
                is_core = any(require_plugin.startswith(m) for m in settings.CORE_MODULES)
                if require_plugin not in request.event.get_plugins() and not is_core:
                    raise Http404(_('This feature is not enabled.'))

            for receiver, response in process_request.send(request.event, request=request):
                if response:
                    return response

    except Event.DoesNotExist:
        if hasattr(request, 'organizer_domain'):
            event = request.organizer.events.get(
                slug__iexact=url.kwargs['event'],
                organizer=request.organizer,
            )
            pathparts = request.get_full_path().split('/')
            pathparts[1] = event.slug
            return redirect('/'.join(pathparts))
        else:
            if 'event' in url.kwargs and 'organizer' in url.kwargs:
                event = Event.objects.select_related('organizer').get(
                    slug__iexact=url.kwargs['event'],
                    organizer__slug__iexact=url.kwargs['organizer']
                )
                pathparts = request.get_full_path().split('/')
                pathparts[1] = event.organizer.slug
                pathparts[2] = event.slug
                return redirect('/'.join(pathparts))
            elif 'organizer' in url.kwargs:
                organizer = Organizer.objects.get(
                    slug__iexact=url.kwargs['organizer']
                )
                pathparts = request.get_full_path().split('/')
                pathparts[1] = organizer.slug
                return redirect('/'.join(pathparts))
        raise Http404(_('The selected event was not found.'))
    except Organizer.DoesNotExist:
        raise Http404(_('The selected organizer was not found.'))

    request._event_detected = True


def _event_view(function=None, require_live=True, require_plugin=None):
    def event_view_wrapper(func, require_live=require_live):
        def wrap(request, *args, **kwargs):
            ret = _detect_event(request, require_live=require_live, require_plugin=require_plugin)
            if ret:
                return ret
            else:
                response = func(request=request, *args, **kwargs)
                for receiver, r in process_response.send(request.event, request=request, response=response):
                    response = r
                return response

        for attrname in dir(func):
            # Preserve flags like csrf_exempt
            if not attrname.startswith('__'):
                setattr(wrap, attrname, getattr(func, attrname))
        return wrap

    if function:
        return event_view_wrapper(function, require_live=require_live)
    return event_view_wrapper


def event_view(function=None, require_live=True):
    warnings.warn('The event_view decorator is deprecated since it will be automatically applied by the URL routing '
                  'layer when you use event_urls.',
                  DeprecationWarning)

    def noop(fn):
        return fn

    return function or noop
