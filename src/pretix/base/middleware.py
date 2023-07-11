#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from collections import OrderedDict
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.middleware.common import CommonMiddleware
from django.urls import get_script_prefix, resolve
from django.utils import timezone, translation
from django.utils.cache import patch_vary_headers
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation.trans_real import (
    check_for_language, get_supported_language_variant, language_code_re,
    parse_accept_lang_header,
)

from pretix.base.i18n import get_language_without_region
from pretix.base.settings import global_settings_object
from pretix.multidomain.urlreverse import (
    get_event_domain, get_organizer_domain,
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
        if not request.path.startswith(get_script_prefix() + 'control'):
            if hasattr(request, 'event'):
                settings_holder = request.event
            elif hasattr(request, 'organizer'):
                settings_holder = request.organizer
            else:
                settings_holder = None

            if settings_holder:
                if language not in settings_holder.settings.locales:
                    firstpart = language.split('-')[0]
                    if firstpart in settings_holder.settings.locales:
                        language = firstpart
                    else:
                        language = settings_holder.settings.locale
                        for lang in settings_holder.settings.locales:
                            if lang.startswith(firstpart + '-'):
                                language = lang
                                break
                if language not in settings_holder.settings.locales:
                    # This seems redundant, but can happen in the rare edge case that settings.locale is (wrongfully)
                    # not part of settings.locales
                    language = settings_holder.settings.locales[0]
                if '-' not in language and settings_holder.settings.region:
                    language += '-' + settings_holder.settings.region
        else:
            gs = global_settings_object(request)
            if '-' not in language and gs.settings.region:
                language += '-' + gs.settings.region

        translation.activate(language)
        request.LANGUAGE_CODE = get_language_without_region()

        tzname = None
        if hasattr(request, 'event'):
            tzname = request.event.settings.timezone
        elif hasattr(request, 'organizer') and 'timezone' in request.organizer.settings._cache():
            tzname = request.organizer.settings.timezone
        elif request.user.is_authenticated:
            tzname = request.user.timezone
        if tzname:
            try:
                timezone.activate(ZoneInfo(tzname))
                request.timezone = tzname
            except ZoneInfoNotFoundError:
                pass
        else:
            timezone.deactivate()

    def process_response(self, request: HttpRequest, response: HttpResponse):
        language = translation.get_language()
        patch_vary_headers(response, ('Accept-Language',))
        if 'Content-Language' not in response:
            response['Content-Language'] = language
        return response


def get_language_from_customer_settings(request: HttpRequest) -> str:
    if getattr(request, 'customer', None):
        lang_code = request.customer.locale
        if lang_code in _supported and lang_code is not None and check_for_language(lang_code):
            return lang_code


def get_language_from_user_settings(request: HttpRequest) -> str:
    if request.user.is_authenticated:
        lang_code = request.user.locale
        if lang_code in _supported and lang_code is not None and check_for_language(lang_code):
            return lang_code


def get_language_from_cookie(request: HttpRequest) -> str:
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
    accept = request.headers.get('Accept-Language', '')
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

    if request.path.startswith(get_script_prefix() + 'control'):
        return (
            get_language_from_user_settings(request)
            or get_language_from_customer_settings(request)
            or get_language_from_cookie(request)
            or get_language_from_browser(request)
            or get_language_from_event(request)
            or get_default_language()
        )
    else:
        return (
            get_language_from_cookie(request)
            or get_language_from_customer_settings(request)
            or get_language_from_user_settings(request)
            or get_language_from_browser(request)
            or get_language_from_event(request)
            or get_default_language()
        )


def _parse_csp(header):
    h = {}
    for part in header.split(';'):
        k, v = part.strip().split(' ', 1)
        h[k.strip()] = v.split(' ')
    return h


def _render_csp(h):
    return "; ".join(k + ' ' + ' '.join(v) for k, v in h.items() if v)


def _merge_csp(a, b):
    for k, v in a.items():
        if k in b:
            a[k] += [i for i in b[k] if i not in a[k]]

    for k, v in b.items():
        if k not in a:
            a[k] = b[k]

    for k, v in a.items():
        if "'unsafe-inline'" in v:
            # If we need unsafe-inline, drop any hashes or nonce as they will be ignored otherwise
            a[k] = [i for i in v if not i.startswith("'nonce-") and not i.startswith("'sha-")]


class SecurityMiddleware(MiddlewareMixin):
    CSP_EXEMPT = (
        '/api/v1/docs/',
    )

    def process_response(self, request, resp):
        url = resolve(request.path_info)

        if settings.DEBUG and resp.status_code >= 400:
            # Don't use CSP on debug error page as it breaks of Django's fancy error
            # pages
            return resp

        resp['X-XSS-Protection'] = '1'

        # We just need to have a P3P, not matter whats in there
        # https://blogs.msdn.microsoft.com/ieinternals/2013/09/17/a-quick-look-at-p3p/
        # https://github.com/pretix/pretix/issues/765
        resp['P3P'] = 'CP=\"ALL DSP COR CUR ADM TAI OUR IND COM NAV INT\"'

        img_src = []
        gs = global_settings_object(request)
        if gs.settings.leaflet_tiles:
            img_src.append(gs.settings.leaflet_tiles[:gs.settings.leaflet_tiles.index("/", 10)].replace("{s}", "*"))

        h = {
            'default-src': ["{static}"],
            'script-src': ['{static}'],
            'object-src': ["'none'"],
            'frame-src': ['{static}'],
            'style-src': ["{static}", "{media}"],
            'connect-src': ["{dynamic}", "{media}"],
            'img-src': ["{static}", "{media}", "data:"] + img_src,
            'font-src': ["{static}"],
            'media-src': ["{static}", "data:"],
            # form-action is not only used to match on form actions, but also on URLs
            # form-actions redirect to. In the context of e.g. payment providers or
            # single-sign-on this can be nearly anything, so we cannot really restrict
            # this. However, we'll restrict it to HTTPS.
            'form-action': ["{dynamic}", "https:"] + (['http:'] if settings.SITE_URL.startswith('http://') else []),
        }
        # Only include pay.google.com for wallet detection purposes on the Payment selection page
        if (
                url.url_name == "event.order.pay.change" or
                (url.url_name == "event.checkout" and url.kwargs['step'] == "payment")
        ):
            h['script-src'].append('https://pay.google.com')
        if settings.LOG_CSP:
            h['report-uri'] = ["/csp_report/"]
        if 'Content-Security-Policy' in resp:
            _merge_csp(h, _parse_csp(resp['Content-Security-Policy']))
        if settings.CSP_ADDITIONAL_HEADER:
            _merge_csp(h, _parse_csp(settings.CSP_ADDITIONAL_HEADER))

        staticdomain = "'self'"
        dynamicdomain = "'self'"
        mediadomain = "'self'"
        if settings.MEDIA_URL.startswith('http'):
            mediadomain += " " + settings.MEDIA_URL[:settings.MEDIA_URL.find('/', 9)]
        if settings.STATIC_URL.startswith('http'):
            staticdomain += " " + settings.STATIC_URL[:settings.STATIC_URL.find('/', 9)]
        if settings.SITE_URL.startswith('http'):
            if settings.SITE_URL.find('/', 9) > 0:
                staticdomain += " " + settings.SITE_URL[:settings.SITE_URL.find('/', 9)]
                dynamicdomain += " " + settings.SITE_URL[:settings.SITE_URL.find('/', 9)]
            else:
                staticdomain += " " + settings.SITE_URL
                dynamicdomain += " " + settings.SITE_URL

        if hasattr(request, 'organizer') and request.organizer:
            if hasattr(request, 'event') and request.event:
                domain = get_event_domain(request.event, fallback=True)
            else:
                domain = get_organizer_domain(request.organizer)
            if domain:
                siteurlsplit = urlsplit(settings.SITE_URL)
                if siteurlsplit.port and siteurlsplit.port not in (80, 443):
                    domain = '%s:%d' % (domain, siteurlsplit.port)
                dynamicdomain += " " + domain

        if request.path not in self.CSP_EXEMPT and not getattr(resp, '_csp_ignore', False):
            resp['Content-Security-Policy'] = _render_csp(h).format(static=staticdomain, dynamic=dynamicdomain,
                                                                    media=mediadomain)
            for k, v in h.items():
                h[k] = sorted(set(' '.join(v).format(static=staticdomain, dynamic=dynamicdomain, media=mediadomain).split(' ')))
            resp['Content-Security-Policy'] = _render_csp(h)
        elif 'Content-Security-Policy' in resp:
            del resp['Content-Security-Policy']

        return resp


class CustomCommonMiddleware(CommonMiddleware):

    def get_full_path_with_slash(self, request):
        """
        Raise an error regardless of DEBUG mode when in POST, PUT, or PATCH.
        """
        new_path = super().get_full_path_with_slash(request)
        if request.method in ('POST', 'PUT', 'PATCH'):
            raise Http404('Please append a / at the end of the URL')
        return new_path
