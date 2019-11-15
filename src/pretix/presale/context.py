from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.translation import get_language_info
from django_scopes import get_scope
from i18nfield.strings import LazyI18nString

from pretix.base.settings import GlobalSettingsObject
from pretix.helpers.i18n import (
    get_javascript_format_without_seconds, get_moment_locale,
)

from .signals import footer_link, html_footer, html_head, html_page_header


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
    _html_page_header = []
    _html_foot = []
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

    if hasattr(request, 'event') and get_scope():
        for receiver, response in html_head.send(request.event, request=request):
            _html_head.append(response)
        for receiver, response in html_page_header.send(request.event, request=request):
            _html_page_header.append(response)
        for receiver, response in html_footer.send(request.event, request=request):
            _html_foot.append(response)
        for receiver, response in footer_link.send(request.event, request=request):
            if isinstance(response, list):
                _footer += response
            else:
                _footer.append(response)

        if request.event.settings.presale_css_file:
            ctx['css_file'] = default_storage.url(request.event.settings.presale_css_file)

        ctx['event_logo'] = request.event.settings.get('logo_image', as_type=str, default='')[7:]
        ctx['social_image'] = request.event.cache.get_or_set(
            'social_image_url',
            request.event.social_image,
            60
        )

        ctx['event'] = request.event
        ctx['languages'] = [get_language_info(code) for code in request.event.settings.locales]

        if request.resolver_match:
            ctx['cart_namespace'] = request.resolver_match.kwargs.get('cart_namespace', '')
    elif hasattr(request, 'organizer'):
        ctx['languages'] = [get_language_info(code) for code in request.organizer.settings.locales]

    if hasattr(request, 'organizer'):
        if request.organizer.settings.presale_css_file and not hasattr(request, 'event'):
            ctx['css_file'] = default_storage.url(request.organizer.settings.presale_css_file)
        ctx['organizer_logo'] = request.organizer.settings.get('organizer_logo_image', as_type=str, default='')[7:]
        ctx['organizer_homepage_text'] = request.organizer.settings.get('organizer_homepage_text', as_type=LazyI18nString)
        ctx['organizer'] = request.organizer

    ctx['html_head'] = "".join(_html_head)
    ctx['html_foot'] = "".join(_html_foot)
    ctx['html_page_header'] = "".join(_html_page_header)
    ctx['footer'] = _footer
    ctx['site_url'] = settings.SITE_URL

    ctx['js_datetime_format'] = get_javascript_format_without_seconds('DATETIME_INPUT_FORMATS')
    ctx['js_date_format'] = get_javascript_format_without_seconds('DATE_INPUT_FORMATS')
    ctx['js_time_format'] = get_javascript_format_without_seconds('TIME_INPUT_FORMATS')
    ctx['js_locale'] = get_moment_locale()
    ctx['settings'] = pretix_settings
    ctx['django_settings'] = settings

    return ctx
