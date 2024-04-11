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

import threading
from contextlib import contextmanager

from dateutil.parser import parse
from django.utils.timezone import now

tls = threading.local()


@contextmanager
def time_machine_now_assigned_from_request(request):
    print("time_machine_now_assigned_from_request")
    if hasattr(request, 'event') and 'timemachine_now_dt' in request.session and \
            request.event.testmode and request.user.is_authenticated and \
            request.user.has_event_permission(request.organizer, request.event, 'can_change_event_settings', request):
        request.now_dt = parse(request.session['timemachine_now_dt'])
        request.now_dt_is_fake = True
    else:
        request.now_dt = now()
        request.now_dt_is_fake = False

    try:
        tls.now_dt = request.now_dt if request.now_dt_is_fake else None

        yield
    finally:
        tls.now_dt = None


def time_machine_now(default=False):
    if default is False:
        default = now()
    return getattr(tls, 'now_dt', None) or default


@contextmanager
def time_machine_now_assigned(now_dt):
    try:
        tls.now_dt = now_dt
        yield
    finally:
        tls.now_dt = None
