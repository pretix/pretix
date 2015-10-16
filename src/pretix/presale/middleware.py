from urllib.parse import urljoin

from django.core.urlresolvers import resolve
from django.http import Http404
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event
from pretix.multidomain.urlreverse import get_domain


class EventMiddleware:
    def process_request(self, request):
        url = resolve(request.path_info)
        url_namespace = url.namespace
        url_name = url.url_name
        if url_namespace != 'presale':
            return

        if 'event.' in url_name and 'event' in url.kwargs:
            try:
                if hasattr(request, 'organizer'):
                    # We are on an organizer's custom domain
                    if 'organizer' in url.kwargs and url.kwargs['organizer']:
                        if url.kwargs['organizer'] != request.organizer.slug:
                            raise Http404(_('The selected event was not found.'))
                        path = "/" + request.get_full_path().split("/", 2)[-1]
                        return redirect(path)

                    request.event = Event.objects.current.filter(
                        slug=url.kwargs['event'],
                        organizer=request.organizer,
                    ).select_related('organizer')[0]
                else:
                    # We are on our main domain
                    if 'organizer' not in url.kwargs:
                        raise Http404(_('The selected event was not found.'))

                    request.event = Event.objects.current.filter(
                        slug=url.kwargs['event'],
                        organizer__slug=url.kwargs['organizer']
                    ).select_related('organizer')[0]

                    # If this organizer has a custom domain, send the user there
                    domain = get_domain(request.event)
                    if domain:
                        if request.port and request.port not in (80, 443):
                            domain = '%s:%d' % (domain, request.port)
                        path = request.get_full_path().split("/", 2)[-1]
                        return redirect(urljoin('%s://%s' % (request.scheme, domain), path))

            except IndexError:
                raise Http404(_('The selected event was not found.'))

        if '_' not in request.session:
            # We need to create session even if we do not yet store something there, because we need the session
            # key for e.g. saving the user's cart
            request.session['_'] = '_'
