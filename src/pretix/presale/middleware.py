from django.template.response import TemplateResponse
from django.urls import resolve
from django_scopes import scope

from pretix.presale.signals import process_response

from .utils import _detect_event


class EventMiddleware:
    NO_REQUIRE_LIVE_URLS = {
        'event.widget.productlist',
        'event.widget.css',
    }

    def __init__(self, get_response=None):
        self.get_response = get_response
        super().__init__()

    def __call__(self, request):
        url = resolve(request.path_info)
        request._namespace = url.namespace
        if url.namespace != 'presale':
            return self.get_response(request)

        if 'organizer' in url.kwargs or 'event' in url.kwargs or getattr(request, 'event_domain', False) or getattr(
                request, 'organizer_domain', False
        ):
            redirect = _detect_event(request, require_live=url.url_name not in self.NO_REQUIRE_LIVE_URLS)
            if redirect:
                return redirect

        with scope(organizer=getattr(request, 'organizer', None)):
            response = self.get_response(request)

            if hasattr(request, '_namespace') and request._namespace == 'presale' and hasattr(request, 'event'):
                for receiver, r in process_response.send(request.event, request=request, response=response):
                    response = r

            if isinstance(response, TemplateResponse):
                response = response.render()

        return response
