from django.conf import settings
from django.core.urlresolvers import resolve


def contextprocessor(request):
    """
    Adds data to all template contexts
    """
    ctx = {
        'url_name': resolve(request.path_info).url_name,
        'settings': settings,
    }

    return ctx
