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
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from urllib.parse import quote, urljoin, urlparse

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME, logout
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, resolve_url
from django.template.response import TemplateResponse
from django.urls import get_script_prefix, resolve, reverse
from django.utils.encoding import force_str
from django.utils.translation import gettext as _
from django_scopes import scope

from pretix.base.models import Event, Organizer
from pretix.base.models.auth import SuperuserPermissionSet, User
from pretix.helpers.security import (
    SessionInvalid, SessionReauthRequired, assert_session_valid,
)


class PermissionMiddleware:
    """
    This middleware enforces all requests to the control app to require login.
    Additionally, it enforces all requests to "control:event." URLs
    to be for an event the user has basic access to.
    """

    EXCEPTIONS = (
        "auth.login",
        "auth.login.2fa",
        "auth.register",
        "auth.forgot",
        "auth.forgot.recover",
        "auth.invite",
        "user.settings.notifications.off",
    )

    EXCEPTIONS_FORCED_PW_CHANGE = (
        "user.settings",
        "auth.logout"
    )

    EXCEPTIONS_2FA = (
        "user.settings.2fa",
        "user.settings.2fa.add",
        "user.settings.2fa.enable",
        "user.settings.2fa.disable",
        "user.settings.2fa.regenemergency",
        "user.settings.2fa.confirm.totp",
        "user.settings.2fa.confirm.webauthn",
        "user.settings.2fa.delete",
        "auth.logout",
        "user.reauth"
    )

    def __init__(self, get_response=None):
        self.get_response = get_response
        super().__init__()

    def _login_redirect(self, request):
        # Taken from django/contrib/auth/decorators.py
        path = request.build_absolute_uri()
        # urlparse chokes on lazy objects in Python 3, force to str
        resolved_login_url = force_str(
            resolve_url(settings.LOGIN_URL_CONTROL))
        # If the login url is the same scheme and net location then just
        # use the path as the "next" url.
        login_scheme, login_netloc = urlparse(resolved_login_url)[:2]
        current_scheme, current_netloc = urlparse(path)[:2]
        if ((not login_scheme or login_scheme == current_scheme) and
                (not login_netloc or login_netloc == current_netloc)):
            path = request.get_full_path()
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(
            path, resolved_login_url, REDIRECT_FIELD_NAME)

    def __call__(self, request):
        url = resolve(request.path_info)
        url_name = url.url_name

        if not request.path.startswith(get_script_prefix() + 'control') and not (url.namespace.startswith("api-") and url_name == "authorize"):
            # This middleware should only touch the /control subpath
            return self.get_response(request)

        if hasattr(request, 'organizer'):
            # If the user is on a organizer's subdomain, he should be redirected to pretix
            return redirect(urljoin(settings.SITE_URL, request.get_full_path()))
        if url_name in self.EXCEPTIONS:
            return self.get_response(request)
        if not request.user.is_authenticated:
            return self._login_redirect(request)

        try:
            # If this logic is updated, make sure to also update the logic in pretix/api/auth/permission.py
            assert_session_valid(request)
        except SessionInvalid:
            logout(request)
            return self._login_redirect(request)
        except SessionReauthRequired:
            if url_name not in ('user.reauth', 'auth.logout'):
                return redirect(reverse('control:user.reauth') + '?next=' + quote(request.get_full_path()))

        if request.user.needs_password_change and url_name not in self.EXCEPTIONS_FORCED_PW_CHANGE:
            return redirect(reverse('control:user.settings') + '?next=' + quote(request.get_full_path()))

        if not request.user.require_2fa and settings.PRETIX_OBLIGATORY_2FA \
                and url_name not in self.EXCEPTIONS_2FA:
            return redirect(reverse('control:user.settings.2fa'))

        if 'event' in url.kwargs and 'organizer' in url.kwargs:
            if url.kwargs['organizer'] == '-' and url.kwargs['event'] == '-':
                # This is a hack that just takes the user to ANY event. It's useful to link to features in support
                # or documentation.
                ev = request.user.get_events_with_any_permission().order_by('-date_from').first()
                if not ev:
                    raise Http404(_("The selected event was not found or you "
                                    "have no permission to administrate it."))
                k = dict(url.kwargs)
                k['organizer'] = ev.organizer.slug
                k['event'] = ev.slug
                return redirect(reverse(url.view_name, kwargs=k, args=url.args))

            with scope(organizer=None):
                request.event = Event.objects.filter(
                    slug=url.kwargs['event'],
                    organizer__slug=url.kwargs['organizer'],
                ).select_related('organizer').first()
            if not request.event or not request.user.has_event_permission(request.event.organizer, request.event,
                                                                          request=request):
                raise Http404(_("The selected event was not found or you "
                                "have no permission to administrate it."))
            request.organizer = request.event.organizer
            if request.user.has_active_staff_session(request.session.session_key):
                request.eventpermset = SuperuserPermissionSet()
            else:
                request.eventpermset = request.user.get_event_permission_set(request.organizer, request.event)
        elif 'organizer' in url.kwargs:
            if url.kwargs['organizer'] == '-':
                # This is a hack that just takes the user to ANY organizer. It's useful to link to features in support
                # or documentation.
                org = request.user.get_organizers_with_any_permission().first()
                if not org:
                    raise Http404(_("The selected organizer was not found or you "
                                    "have no permission to administrate it."))
                k = dict(url.kwargs)
                k['organizer'] = org.slug
                return redirect(reverse(url.view_name, kwargs=k, args=url.args))

            request.organizer = Organizer.objects.filter(
                slug=url.kwargs['organizer'],
            ).first()
            if not request.organizer or not request.user.has_organizer_permission(request.organizer, request=request):
                raise Http404(_("The selected organizer was not found or you "
                                "have no permission to administrate it."))
            if request.user.has_active_staff_session(request.session.session_key):
                request.orgapermset = SuperuserPermissionSet()
            else:
                request.orgapermset = request.user.get_organizer_permission_set(request.organizer)

        with scope(organizer=getattr(request, 'organizer', None)):
            r = self.get_response(request)
            if isinstance(r, TemplateResponse):
                r = r.render()
            return r


class AuditLogMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(get_script_prefix() + 'control') and request.user.is_authenticated:
            if getattr(request.user, "is_hijacked", False):
                hijack_history = request.session.get('hijack_history', False)
                hijacker = get_object_or_404(User, pk=hijack_history[0])
                ss = hijacker.get_active_staff_session(request.session.get('hijacker_session'))
                if ss:
                    ss.logs.create(
                        url=request.path,
                        method=request.method,
                        impersonating=request.user
                    )
            else:
                ss = request.user.get_active_staff_session(request.session.session_key)
                if ss:
                    ss.logs.create(
                        url=request.path,
                        method=request.method
                    )

        response = self.get_response(request)
        return response
