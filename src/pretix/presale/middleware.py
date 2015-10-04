from django.core.urlresolvers import resolve
from django.http import Http404
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event


class EventMiddleware:
    def process_request(self, request):
        url = resolve(request.path_info)
        url_namespace = url.namespace
        url_name = url.url_name
        if url_namespace != 'presale':
            return

        if 'event.' in url_name and 'event' in url.kwargs:
            try:
                request.event = Event.objects.current.filter(
                    slug=url.kwargs['event'],
                    organizer__slug=url.kwargs['organizer'],
                ).select_related('organizer')[0]
            except IndexError:
                raise Http404(_('The selected event was not found.'))

        if '_' not in request.session:
            # We need to create session even if we do not yet store something there, because we need the session
            # key for e.g. saving the user's cart
            request.session['_'] = '_'
