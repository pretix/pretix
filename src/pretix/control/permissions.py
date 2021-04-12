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

from urllib.parse import quote

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _


def current_url(request):
    if request.GET:
        return request.path + '?' + request.GET.urlencode()
    else:
        return request.path


def event_permission_required(permission):
    """
    This view decorator rejects all requests with a 403 response which are not from
    users having the given permission for the event the request is associated with.
    """
    if permission == 'can_change_settings':
        # Legacy support
        permission = 'can_change_event_settings'

    def decorator(function):
        def wrapper(request, *args, **kw):
            if not request.user.is_authenticated:  # NOQA
                # just a double check, should not ever happen
                raise PermissionDenied()

            allowed = (
                request.user.has_event_permission(request.organizer, request.event, permission, request=request)
            )
            if allowed:
                return function(request, *args, **kw)

            raise PermissionDenied(_('You do not have permission to view this content.'))
        return wrapper
    return decorator


class EventPermissionRequiredMixin:
    """
    This mixin is equivalent to the event_permission_required view decorator but
    is in a form suitable for class-based views.
    """
    permission = ''

    @classmethod
    def as_view(cls, **initkwargs):
        view = super(EventPermissionRequiredMixin, cls).as_view(**initkwargs)
        return event_permission_required(cls.permission)(view)


def organizer_permission_required(permission):
    """
    This view decorator rejects all requests with a 403 response which are not from
    users having the given permission for the event the request is associated with.
    """
    if permission == 'can_change_settings':
        # Legacy support
        permission = 'can_change_organizer_settings'

    def decorator(function):
        def wrapper(request, *args, **kw):
            if not request.user.is_authenticated:  # NOQA
                # just a double check, should not ever happen
                raise PermissionDenied()

            allowed = request.user.has_organizer_permission(request.organizer, permission, request=request)
            if allowed:
                return function(request, *args, **kw)

            raise PermissionDenied(_('You do not have permission to view this content.'))
        return wrapper
    return decorator


class OrganizerPermissionRequiredMixin:
    """
    This mixin is equivalent to the organizer_permission_required view decorator but
    is in a form suitable for class-based views.
    """
    permission = ''

    @classmethod
    def as_view(cls, **initkwargs):
        view = super(OrganizerPermissionRequiredMixin, cls).as_view(**initkwargs)
        return organizer_permission_required(cls.permission)(view)


def administrator_permission_required():
    """
    This view decorator rejects all requests with a 403 response which are not from
    users with a current staff member session.
    """
    def decorator(function):
        def wrapper(request, *args, **kw):
            if not request.user.is_authenticated:  # NOQA
                # just a double check, should not ever happen
                raise PermissionDenied()
            if not request.user.has_active_staff_session(request.session.session_key):
                if request.user.is_staff:
                    return redirect(reverse('control:user.sudo') + '?next=' + quote(current_url(request)))
                raise PermissionDenied(_('You do not have permission to view this content.'))
            return function(request, *args, **kw)
        return wrapper
    return decorator


def staff_member_required():
    """
    This view decorator rejects all requests with a 403 response which are not staff
    members (but do not need to have an active session).
    """
    def decorator(function):
        def wrapper(request, *args, **kw):
            if not request.user.is_authenticated:  # NOQA
                # just a double check, should not ever happen
                raise PermissionDenied()
            if not request.user.is_staff:
                raise PermissionDenied(_('You do not have permission to view this content.'))
            return function(request, *args, **kw)
        return wrapper
    return decorator


class AdministratorPermissionRequiredMixin:
    """
    This mixin is equivalent to the administrator_permission_required view decorator but
    is in a form suitable for class-based views.
    """
    @classmethod
    def as_view(cls, **initkwargs):
        view = super(AdministratorPermissionRequiredMixin, cls).as_view(**initkwargs)
        return administrator_permission_required()(view)


class StaffMemberRequiredMixin:
    """
    This mixin is equivalent to the staff_memer_required view decorator but
    is in a form suitable for class-based views.
    """
    @classmethod
    def as_view(cls, **initkwargs):
        view = super(StaffMemberRequiredMixin, cls).as_view(**initkwargs)
        return staff_member_required()(view)
