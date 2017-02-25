from django.conf import settings
from django.core.files.storage import default_storage
from i18nfield.strings import LazyI18nString

from pretix.base.settings import GlobalSettingsObject

from .signals import footer_link, html_head


def contextprocessor(request):
    """
    Adds data to all template contexts
    """
    if request.path.startswith('/control'):
        return {}

    ctx = {
        'css_file': None,
        'DEBUG': settings.DEBUG,
    }
    _html_head = []
    _footer = []

    if hasattr(request, 'event'):
        pretix_settings = request.event.settings
    elif hasattr(request, 'organizer'):
        pretix_settings = request.organizer.settings
    else:
        pretix_settings = GlobalSettingsObject().settings

    text = pretix_settings.get('footer_text', as_type=LazyI18nString)
    link = pretix_settings.get('footer_link', as_type=LazyI18nString)

    if text:
        if link:
            _footer.append({'url': str(link), 'label': str(text)})
        else:
            ctx['footer_text'] = str(text)

    if hasattr(request, 'event'):
        for receiver, response in html_head.send(request.event, request=request):
            _html_head.append(response)
        for receiver, response in footer_link.send(request.event, request=request):
            if isinstance(response, list):
                _footer += response
            else:
                _footer.append(response)

        if request.event.settings.presale_css_file:
            ctx['css_file'] = default_storage.url(request.event.settings.presale_css_file)
        ctx['event_logo'] = request.event.settings.get('logo_image', as_type=str, default='')[7:]
        ctx['event'] = request.event

    ctx['html_head'] = "".join(_html_head)
    ctx['footer'] = _footer
    ctx['site_url'] = settings.SITE_URL

    return ctx
