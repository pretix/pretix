from django.conf import settings
from django.core.urlresolvers import resolve
from django.utils.encoding import force_str
from django.utils.six.moves.urllib.parse import urlparse
from django.shortcuts import resolve_url
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.http import HttpResponseNotFound
from django.utils.translation import ugettext as _

from pretixbase.models import Event


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
                return HttpResponseNotFound()  # TODO: Provide error message
