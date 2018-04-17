from django.http import HttpResponse
from django.views.decorators.cache import cache_page


class NoSearchIndexViewMixin:
    def dispatch(self, request, *args, **kwargs):
        resp = super().dispatch(request, *args, **kwargs)
        resp['X-Robots-Tag'] = "noindex"
        return resp


@cache_page(3600)
def robots_txt(request):
    return HttpResponse(
        """User-agent: *
Disallow: */cart/*
Disallow: */checkout/*
Disallow: */order/*
Disallow: */locale/set*
Disallow: /control/
Disallow: /download/
Disallow: /redirect/
Disallow: /api/
""", content_type='text/plain'
    )
