from django.core.urlresolvers import resolve

from .utils import _detect_event


class EventMiddleware:
    def process_request(self, request):
        url = resolve(request.path_info)
        url_namespace = url.namespace
        if url_namespace != 'presale':
            return

        if 'organizer' in url.kwargs or 'event' in url.kwargs:
            redirect = _detect_event(request)
            if redirect:
                return redirect

        if '_' not in request.session:
            # We need to create session even if we do not yet store something there, because we need the session
            # key for e.g. saving the user's cart
            request.session['_'] = '_'
