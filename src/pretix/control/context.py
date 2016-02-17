from django.conf import settings
from django.core.urlresolvers import Resolver404, get_script_prefix, resolve

from .signals import html_head, nav_event


def contextprocessor(request):
    """
    Adds data to all template contexts
    """
    try:
        url = resolve(request.path_info)
    except Resolver404:
        return {}

    if not request.path.startswith(get_script_prefix() + 'control'):
        return {}
    ctx = {
        'url_name': url.url_name,
        'settings': settings,
    }
    _html_head = []
    if hasattr(request, 'event'):
        for receiver, response in html_head.send(request.event, request=request):
            _html_head.append(response)
    ctx['html_head'] = "".join(_html_head)

    _nav_event = []
    if hasattr(request, 'event'):
        for receiver, response in nav_event.send(request.event, request=request):
            _nav_event += response
    ctx['nav_event'] = _nav_event
    return ctx
