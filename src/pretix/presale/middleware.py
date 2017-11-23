from django.core.urlresolvers import resolve

from pretix.presale.signals import process_response

from .utils import _detect_event


class EventMiddleware:

    def __init__(self, get_response, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.get_response = get_response

    def process_request(self, request):
        url = resolve(request.path_info)
        request._namespace = url.namespace
        if url.namespace != 'presale':
            return

        if 'organizer' in url.kwargs or 'event' in url.kwargs:
            redirect = _detect_event(request)
            if redirect:
                return redirect

    def process_response(self, request, response):
        if hasattr(request, '_namespace') and request._namespace == 'presale' and hasattr(request, 'event'):
            for receiver, r in process_response.send(request.event, request=request, response=response):
                response = r
        return response

    def __call__(self, request):
        self.process_request(request)
        response = self.get_response(request)
        return self.process_response(request, response)
