from django.conf import settings
from django.core.urlresolvers import resolve


def contextprocessor(request):
    return {
        'url_name': resolve(request.path_info).url_name,
        'settings': settings,
    }
