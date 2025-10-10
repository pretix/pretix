#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
import contextvars
from contextlib import contextmanager

from dateutil.parser import parse
from django.utils.timezone import now

from pretix.base.auth import has_event_access_permission

timemachine_now_var = contextvars.ContextVar('timemachine_now', default=None)


@contextmanager
def time_machine_now_assigned_from_request(request):
    if hasattr(request, 'event') and f'timemachine_now_dt:{request.event.pk}' in request.session and \
            request.event.testmode and has_event_access_permission(request):
        request.now_dt = parse(request.session[f'timemachine_now_dt:{request.event.pk}'])
        request.now_dt_is_fake = True
    else:
        request.now_dt = now()
        request.now_dt_is_fake = False

    try:
        timemachine_now_var.set(request.now_dt if request.now_dt_is_fake else None)

        yield
    finally:
        timemachine_now_var.set(None)


def time_machine_now(default=False):
    """
    Return the datetime to use as current datetime for checking order restrictions in event
    index and checkout flow.

    :param default:   Value to return if time machine mode is disabled. By default the current datetime is used.
    """
    if default is False:
        default = now()
    return timemachine_now_var.get() or default


@contextmanager
def time_machine_now_assigned(now_dt):
    """
    Use this context manager to assign current datetime for time machine mode. Useful e.g. for background tasks.

    :param now_dt: The datetime value to assign. May be `None` to disable time machine.
    """
    try:
        timemachine_now_var.set(now_dt)
        yield
    finally:
        timemachine_now_var.set(None)
