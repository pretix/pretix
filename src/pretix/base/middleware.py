from collections import OrderedDict

import pytz
from django.conf import settings
from django.core.urlresolvers import get_script_prefix
from django.http import HttpRequest, HttpResponse
from django.utils import timezone, translation
from django.utils.cache import patch_vary_headers
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import LANGUAGE_SESSION_KEY
from django.utils.translation.trans_real import (
    check_for_language, get_supported_language_variant, language_code_re,
    parse_accept_lang_header,
)

_supported = None


class LocaleMiddleware(MiddlewareMixin):

    """
    This middleware sets the correct locale and timezone
    for a request.
    """

    def process_request(self, request: HttpRequest):
        language = get_language_from_request(request)
        # Normally, this middleware runs *before* the event is set. However, on event frontend pages it
        # might be run a second time by pretix.presale.EventMiddleware and in this case the event is already
        # set and can be taken into account for the decision.
        if hasattr(request, 'event') and not request.path.startswith(get_script_prefix() + 'control'):
            if language not in request.event.settings.locales:
                firstpart = language.split('-')[0]
                if firstpart in request.event.settings.locales:
                    language = firstpart
                else:
                    language = request.event.settings.locale
                    for lang in request.event.settings.locales:
                        if lang.startswith(firstpart + '-'):
                            language = lang
                            break
        translation.activate(language)
        request.LANGUAGE_CODE = translation.get_language()

        tzname = None
        if request.user.is_authenticated:
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

    def process_response(self, request: HttpRequest, response: HttpResponse):
        language = translation.get_language()
        patch_vary_headers(response, ('Accept-Language',))
        if 'Content-Language' not in response:
            response['Content-Language'] = language
        return response


def get_language_from_user_settings(request: HttpRequest) -> str:
    if request.user.is_authenticated:
        lang_code = request.user.locale
        if lang_code in _supported and lang_code is not None and check_for_language(lang_code):
            return lang_code


def get_language_from_session_or_cookie(request: HttpRequest) -> str:
    if hasattr(request, 'session'):
        lang_code = request.session.get(LANGUAGE_SESSION_KEY)
        if lang_code in _supported and lang_code is not None and check_for_language(lang_code):
            return lang_code

    lang_code = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
    try:
        return get_supported_language_variant(lang_code)
    except LookupError:
        pass


def get_language_from_event(request: HttpRequest) -> str:
    if hasattr(request, 'event'):
        lang_code = request.event.settings.locale
        try:
            return get_supported_language_variant(lang_code)
        except LookupError:
            pass


def get_language_from_browser(request: HttpRequest) -> str:
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
    except LookupError:  # NOQA
        return settings.LANGUAGE_CODE


def get_language_from_request(request: HttpRequest) -> str:
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


class SecurityMiddleware(MiddlewareMixin):

    def _parse_csp(self, header):
        h = {}
        for part in header.split(';'):
            k, v = part.strip().split(' ', 1)
            h[k.strip()] = v
        return h

    def _render_csp(self, h):
        return "; ".join(k + ' ' + v for k, v in h.items())

    def process_response(self, request, resp):
        if settings.DEBUG and resp.status_code >= 400:
            # Don't use CSP on debug error page as it breaks of Django's fancy error
            # pages
            return resp

        resp['X-XSS-Protection'] = '1'
        h = {
            'default-src': "{static}",
            'script-src': '{static} https://checkout.stripe.com https://js.stripe.com',
            'object-src': "'none'",
            # frame-src is deprecated but kept for compatibility with CSP 1.0 browsers, e.g. Safari 9
            'frame-src': '{static} https://checkout.stripe.com https://js.stripe.com',
            'child-src': '{static} https://checkout.stripe.com https://js.stripe.com',
            'style-src': "{static}",
            'connect-src': "{dynamic} https://checkout.stripe.com",
            'img-src': "{static} data: https://*.stripe.com",
            # form-action is not only used to match on form actions, but also on URLs
            # form-actions redirect to. In the context of e.g. payment providers or
            # single-sign-on this can be nearly anything so we cannot really restrict
            # this. However, we'll restrict it to HTTPS.
            'form-action': "{dynamic} https:",
        }
        if 'Content-Security-Policy' in resp:
            h.update(self._parse_csp(resp['Content-Security-Policy']))

        staticdomain = "'self'"
        dynamicdomain = "'self'"
        if settings.STATIC_URL.startswith('http'):
            staticdomain += " " + settings.STATIC_URL[:settings.STATIC_URL.find('/', 9)]
        if settings.SITE_URL.startswith('http'):
            if settings.SITE_URL.find('/', 9) > 0:
                staticdomain += " " + settings.SITE_URL[:settings.SITE_URL.find('/', 9)]
                dynamicdomain += " " + settings.SITE_URL[:settings.SITE_URL.find('/', 9)]
            else:
                staticdomain += " " + settings.SITE_URL
                dynamicdomain += " " + settings.SITE_URL
        resp['Content-Security-Policy'] = self._render_csp(h).format(static=staticdomain, dynamic=dynamicdomain)
        return resp
