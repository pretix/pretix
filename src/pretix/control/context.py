from django.conf import settings
from django.core.urlresolvers import resolve
from .signals import html_head


def contextprocessor(request):
    """
    Adds data to all template contexts
    """
    url = resolve(request.path_info)
    if url.namespace != 'control':
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

    return ctx
