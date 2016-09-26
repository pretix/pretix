from django.conf import settings
from django.core.files.storage import default_storage

from .signals import footer_link, html_head


def contextprocessor(request):
    """
    Adds data to all template contexts
    """
    if request.path.startswith('/control'):
        return {}

    ctx = {
        'css_file': None
    }
    _html_head = []
    _footer = []
    if hasattr(request, 'event'):
        for receiver, response in html_head.send(request.event, request=request):
            _html_head.append(response)
        for receiver, response in footer_link.send(request.event, request=request):
            _footer.append(response)

        if request.event.settings.presale_css_file:
            ctx['css_file'] = default_storage.url(request.event.settings.presale_css_file)
        ctx['event_logo'] = request.event.settings.get('logo_image', as_type=str, default='')[7:]
        ctx['event'] = request.event

    ctx['html_head'] = "".join(_html_head)
    ctx['footer'] = _footer
    ctx['site_url'] = settings.SITE_URL

    return ctx
