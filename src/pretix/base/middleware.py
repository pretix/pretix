from django.core.urlresolvers import get_script_prefix
import pytz

from django.conf import settings
from django.middleware.locale import LocaleMiddleware as BaseLocaleMiddleware
from django.utils.translation.trans_real import (
    get_supported_language_variant,
    parse_accept_lang_header,
    language_code_re,
    check_for_language
)
from django.utils.translation import LANGUAGE_SESSION_KEY
from django.utils import translation, timezone
from collections import OrderedDict
from django.utils.cache import patch_vary_headers


_supported = None


class LocaleMiddleware(BaseLocaleMiddleware):

    """
    This middleware sets the correct locale and timezone
    for a request.
    """

    def process_request(self, request):
        language = get_language_from_request(request)
        if hasattr(request, 'event') and not request.path.startswith(get_script_prefix() + 'control'):
            if language not in request.event.settings.locales:
                language = request.event.settings.locale
        translation.activate(language)
        request.LANGUAGE_CODE = translation.get_language()

        tzname = None
        if request.user.is_authenticated():
            tzname = request.user.timezone
        if hasattr(request, 'event'):
            tzname = request.event.settings.timezone
        if tzname:
            try:
                timezone.activate(pytz.timezone(tzname))
                request.timezone = tzname
            except pytz.UnknownTimeZoneError:
                pass
        else:
            timezone.deactivate()

    def process_response(self, request, response):
        language = translation.get_language()
        patch_vary_headers(response, ('Accept-Language',))
        if 'Content-Language' not in response:
            response['Content-Language'] = language
        return response


def get_language_from_user_settings(request) -> str:
    if request.user.is_authenticated():
        lang_code = request.user.locale
        if lang_code in _supported and lang_code is not None and check_for_language(lang_code):
            return lang_code


def get_language_from_session_or_cookie(request) -> str:
    if hasattr(request, 'session'):
        lang_code = request.session.get(LANGUAGE_SESSION_KEY)
        if lang_code in _supported and lang_code is not None and check_for_language(lang_code):
            return lang_code

    lang_code = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
    try:
        return get_supported_language_variant(lang_code)
    except LookupError:
        pass


def get_language_from_event(request) -> str:
    if hasattr(request, 'event'):
        lang_code = request.event.settings.locale
        try:
            return get_supported_language_variant(lang_code)
        except LookupError:
            pass


def get_language_from_browser(request) -> str:
    accept = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    for accept_lang, unused in parse_accept_lang_header(accept):
        if accept_lang == '*':
            break

        if not language_code_re.search(accept_lang):
            continue

        try:
            return get_supported_language_variant(accept_lang)
        except LookupError:
            continue


def get_default_language():
    try:
        return get_supported_language_variant(settings.LANGUAGE_CODE)
    except LookupError:
        return settings.LANGUAGE_CODE


def get_language_from_request(request) -> str:
    """
    Analyzes the request to find what language the user wants the system to
    show. Only languages listed in settings.LANGUAGES are taken into account.
    If the user requests a sublanguage where we have a main language, we send
    out the main language.
    """
    global _supported
    if _supported is None:
        _supported = OrderedDict(settings.LANGUAGES)

    return (
        get_language_from_user_settings(request)
        or get_language_from_session_or_cookie(request)
        or get_language_from_event(request)
        or get_language_from_browser(request)
        or get_default_language()
    )
