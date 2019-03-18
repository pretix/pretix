from django.urls import resolve
from django.utils.deprecation import MiddlewareMixin

from pretix.presale.signals import process_response

from .utils import _detect_event


class EventMiddleware(MiddlewareMixin):
    def process_request(self, request):
        url = resolve(request.path_info)
        request._namespace = url.namespace
        if url.namespace != 'presale':
            return

        if 'organizer' in url.kwargs or 'event' in url.kwargs:
            redirect = _detect_event(request, require_live=url.url_name != 'event.widget.productlist')
            if redirect:
                return redirect

    def process_response(self, request, response):
        if hasattr(request, '_namespace') and request._namespace == 'presale' and hasattr(request, 'event'):
            for receiver, r in process_response.send(request.event, request=request, response=response):
                response = r
        return response
