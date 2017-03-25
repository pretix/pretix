from django.urls import resolve

from pretix.base.metrics import http_view_requests


class MetricsMiddleware(object):
    blacklist = (
        '/healthcheck/',
        '/jsi18n/',
        '/metrics',
    )

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        for b in self.blacklist:
            if b in request.path:
                return self.get_response(request)

        url = resolve(request.path_info)

        resp = self.get_response(request)
        http_view_requests.inc(1, status_code=resp.status_code, method=request.method,
                               url_name=url.namespace + ':' + url.url_name)

        return resp
