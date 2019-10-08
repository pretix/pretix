import time

from django.urls import resolve

from pretix.base.metrics import pretix_view_duration_seconds


class MetricsMiddleware(object):
    banlist = (
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
        for b in self.banlist:
            if b in request.path:
                return self.get_response(request)

        url = resolve(request.path_info)

        t0 = time.perf_counter()
        resp = self.get_response(request)
        tdiff = time.perf_counter() - t0
        pretix_view_duration_seconds.observe(tdiff, status_code=resp.status_code, method=request.method,
                                             url_name=url.namespace + ':' + url.url_name)

        return resp
