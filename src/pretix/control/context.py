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
# This file contains Apache-licensed contributions copyrighted by: Christopher Dambamuromo
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import sys
from importlib import import_module

from django.conf import settings
from django.db.models import Q
from django.urls import Resolver404, get_script_prefix, resolve
from django.utils.translation import get_language
from django_scopes import scope

from pretix.base.models.auth import StaffSession
from pretix.base.settings import GlobalSettingsObject
from pretix.control.navigation import (
    get_event_navigation, get_global_navigation, get_organizer_navigation,
)

from ..helpers.i18n import (
    get_javascript_format, get_javascript_output_format, get_moment_locale,
)
from ..multidomain.urlreverse import get_event_domain
from .signals import html_head, nav_topbar

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore


def contextprocessor(request):
    """
    Adds data to all template contexts
    """
    if not hasattr(request, '_pretix_control_default_context'):
        request._pretix_control_default_context = _default_context(request)
    return request._pretix_control_default_context


def _default_context(request):
    try:
        url = resolve(request.path_info)
    except Resolver404:
        return {}

    if not request.path.startswith(get_script_prefix() + 'control') or not hasattr(request, 'user'):
        return {}
    ctx = {
        'url_name': url.url_name,
        'settings': settings,
        'django_settings': settings,
        'DEBUG': settings.DEBUG,
    }
    _html_head = []
    if hasattr(request, 'event') and request.user.is_authenticated:
        for receiver, response in html_head.send(request.event, request=request):
            _html_head.append(response)
    ctx['html_head'] = "".join(_html_head)

    _js_payment_weekdays_disabled = '[]'
    if getattr(request, 'event', None) and hasattr(request, 'organizer') and request.user.is_authenticated:
        ctx['nav_items'] = get_event_navigation(request)

        if request.event.settings.get('payment_term_weekdays'):
            _js_payment_weekdays_disabled = '[0,6]'

        ctx['has_domain'] = get_event_domain(request.event, fallback=True) is not None

        if not request.event.testmode:
            with scope(organizer=request.organizer):
                complain_testmode_orders = request.event.cache.get('complain_testmode_orders')
                if complain_testmode_orders is None:
                    complain_testmode_orders = request.event.orders.filter(testmode=True).exists()
                    request.event.cache.set('complain_testmode_orders', complain_testmode_orders, 30)
            ctx['complain_testmode_orders'] = complain_testmode_orders and request.user.has_event_permission(
                request.organizer, request.event, 'can_view_orders', request=request
            )
        else:
            ctx['complain_testmode_orders'] = False

        if not request.event.live and ctx['has_domain']:
            child_sess = request.session.get('child_session_{}'.format(request.event.pk))
            s = SessionStore()
            if not child_sess or not s.exists(child_sess):
                s['pretix_event_access_{}'.format(request.event.pk)] = request.session.session_key
                s.create()
                ctx['new_session'] = s.session_key
                request.session['child_session_{}'.format(request.event.pk)] = s.session_key
                request.session['event_access'] = True
            else:
                ctx['new_session'] = child_sess
                request.session['event_access'] = True

        if request.GET.get('subevent', ''):
            # Do not use .get() for lazy evaluation
            ctx['selected_subevents'] = request.event.subevents.filter(pk=request.GET.get('subevent'))
    elif getattr(request, 'organizer', None) and request.user.is_authenticated:
        ctx['nav_items'] = get_organizer_navigation(request)
    elif request.user.is_authenticated:
        ctx['nav_items'] = get_global_navigation(request)

    ctx['js_payment_weekdays_disabled'] = _js_payment_weekdays_disabled

    _nav_topbar = []
    if request.user.is_authenticated:
        for receiver, response in nav_topbar.send(request, request=request):
            _nav_topbar += response
    ctx['nav_topbar'] = sorted(_nav_topbar, key=lambda n: n['label'])

    ctx['js_datetime_format'] = get_javascript_format('DATETIME_INPUT_FORMATS')
    ctx['js_date_format'] = get_javascript_format('DATE_INPUT_FORMATS')
    ctx['js_long_date_format'] = get_javascript_output_format('DATE_FORMAT')
    ctx['js_time_format'] = get_javascript_format('TIME_INPUT_FORMATS')
    ctx['js_locale'] = get_moment_locale()
    ctx['select2locale'] = get_language()[:2]

    ctx['warning_update_available'] = False
    ctx['warning_update_check_active'] = False
    ctx['warning_license_compliance_check_required'] = False
    gs = GlobalSettingsObject()
    ctx['global_settings'] = gs.settings
    if request.user.is_staff:
        if not gs.settings.license_check_completed:
            ctx['warning_license_compliance_check_required'] = True
        if gs.settings.update_check_result_warning:
            ctx['warning_update_available'] = True
        if not gs.settings.update_check_ack and 'runserver' not in sys.argv:
            ctx['warning_update_check_active'] = True

    ctx['ie_deprecation_warning'] = 'MSIE' in request.headers.get('User-Agent', '') or 'Trident/' in request.headers.get('User-Agent', '')

    if request.user.is_authenticated:
        ctx['staff_session'] = request.user.has_active_staff_session(request.session.session_key)
        ctx['staff_need_to_explain'] = (
            StaffSession.objects.filter(user=request.user, date_end__isnull=False).filter(
                Q(comment__isnull=True) | Q(comment="")
            )
            if request.user.is_staff and settings.PRETIX_ADMIN_AUDIT_COMMENTS else StaffSession.objects.none()
        )

    return ctx
