from urllib.parse import urljoin

from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import resolve
from django.http import Http404
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event, EventPermission, Organizer
from pretix.multidomain.urlreverse import get_domain


class EventMiddleware:
    def process_request(self, request):
        url = resolve(request.path_info)
        url_namespace = url.namespace
        if url_namespace != 'presale':
            return

        if 'organizer' in url.kwargs or 'event' in url.kwargs:
            try:
                if hasattr(request, 'organizer'):
                    # We are on an organizer's custom domain
                    if 'organizer' in url.kwargs and url.kwargs['organizer']:
                        if url.kwargs['organizer'] != request.organizer.slug:
                            raise Http404(_('The selected event was not found.'))
                        path = "/" + request.get_full_path().split("/", 2)[-1]
                        return redirect(path)

                    request.event = Event.objects.filter(
                        slug=url.kwargs['event'],
                        organizer=request.organizer,
                    ).select_related('organizer')[0]
                    request.organizer = request.event.organizer
                else:
                    # We are on our main domain
                    if 'event' in url.kwargs and 'organizer' in url.kwargs:
                        request.event = Event.objects.filter(
                            slug=url.kwargs['event'],
                            organizer__slug=url.kwargs['organizer']
                        ).select_related('organizer')[0]
                        request.organizer = request.event.organizer
                    elif 'organizer' in url.kwargs:
                        request.organizer = Organizer.objects.filter(
                            slug=url.kwargs['organizer']
                        )[0]
                    else:
                        raise Http404()

                    # If this organizer has a custom domain, send the user there
                    domain = get_domain(request.organizer)
                    if domain:
                        if request.port and request.port not in (80, 443):
                            domain = '%s:%d' % (domain, request.port)
                        path = request.get_full_path().split("/", 2)[-1]
                        return redirect(urljoin('%s://%s' % (request.scheme, domain), path))

                if hasattr(request, 'event') and not request.event.live:
                    if not request.user.is_authenticated() or not EventPermission.objects.filter(
                            event=request.event, user=request.user).exists():
                        raise PermissionDenied(_('The selected ticket shop is currently not available.'))

            except IndexError:
                raise Http404(_('The selected event or organizer was not found.'))

        if '_' not in request.session:
            # We need to create session even if we do not yet store something there, because we need the session
            # key for e.g. saving the user's cart
            request.session['_'] = '_'
