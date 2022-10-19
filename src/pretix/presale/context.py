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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Bolutife Lawrence, Michele Fattoruso, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import logging

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import translation
from django.utils.translation import get_language_info
from django_scopes import get_scope
from i18nfield.strings import LazyI18nString

from pretix.base.settings import GlobalSettingsObject
from pretix.helpers.i18n import (
    get_javascript_format_without_seconds, get_moment_locale,
)

from ..base.i18n import get_language_without_region
from .cookies import get_cookie_providers
from .signals import (
    footer_link, global_footer_link, global_html_footer, global_html_head,
    global_html_page_header, html_footer, html_head, html_page_header,
)
from .views.cart import cart_session, get_or_create_cart_id

logger = logging.getLogger(__name__)


def contextprocessor(request):
    """
    Adds data to all template contexts
    """
    if not hasattr(request, '_pretix_presale_default_context'):
        request._pretix_presale_default_context = _default_context(request)
    return request._pretix_presale_default_context


def _default_context(request):
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

    if hasattr(request, 'event') and request.event:
        pretix_settings = request.event.settings
    elif hasattr(request, 'organizer') and request.organizer:
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

    for receiver, response in global_html_page_header.send(None, request=request):
        _html_page_header.append(response)
    for receiver, response in global_html_head.send(None, request=request):
        _html_head.append(response)
    for receiver, response in global_html_footer.send(None, request=request):
        _html_foot.append(response)
    for receiver, response in global_footer_link.send(None, request=request):
        if isinstance(response, list):
            _footer += response
        else:
            _footer.append(response)

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
        _footer += request.event.cache.get_or_set('footer_links', lambda: [
            {'url': fl.url, 'label': fl.label}
            for fl in request.event.footer_links.all()
        ], timeout=300)

        if request.event.settings.presale_css_file:
            ctx['css_file'] = default_storage.url(request.event.settings.presale_css_file)

        ctx['event_logo'] = request.event.settings.get('logo_image', as_type=str, default='')[7:]
        ctx['event_logo_image_large'] = request.event.settings.logo_image_large
        ctx['event_logo_show_title'] = request.event.settings.logo_show_title
        if not ctx['event_logo'] and request.event.settings.organizer_logo_image_inherit and request.event.settings.organizer_logo_image:
            ctx['event_logo'] = request.event.settings.get('organizer_logo_image', as_type=str, default='')[7:]
            ctx['event_logo_image_large'] = request.event.settings.organizer_logo_image_large
            ctx['event_logo_show_title'] = True
        try:
            ctx['social_image'] = request.event.cache.get_or_set(
                'social_image_url',
                request.event.social_image,
                60
            )
        except:
            logger.exception('Could not generate social image')

        ctx['event'] = request.event
        ctx['languages'] = [get_language_info(code) for code in request.event.settings.locales]

        ctx['cookie_providers'] = get_cookie_providers(request.event, request)
        if get_or_create_cart_id(request, create=False):
            c = cart_session(request)
            if "widget_data" in c and c["widget_data"].get("consent"):
                ctx['cookie_consent_from_widget'] = c["widget_data"].get("consent").split(",")

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
        _footer += request.organizer.cache.get_or_set('footer_links', lambda: [
            {'url': fl.url, 'label': fl.label}
            for fl in request.organizer.footer_links.all()
        ], timeout=300)

    ctx['html_head'] = "".join(h for h in _html_head if h)
    ctx['html_foot'] = "".join(h for h in _html_foot if h)
    ctx['html_page_header'] = "".join(h for h in _html_page_header if h)
    ctx['footer'] = _footer
    ctx['site_url'] = settings.SITE_URL

    ctx['js_datetime_format'] = get_javascript_format_without_seconds('DATETIME_INPUT_FORMATS')
    ctx['js_date_format'] = get_javascript_format_without_seconds('DATE_INPUT_FORMATS')
    ctx['js_time_format'] = get_javascript_format_without_seconds('TIME_INPUT_FORMATS')
    ctx['js_locale'] = get_moment_locale()
    ctx['html_locale'] = translation.get_language_info(get_language_without_region()).get('public_code', translation.get_language())
    ctx['settings'] = pretix_settings
    ctx['django_settings'] = settings

    return ctx
