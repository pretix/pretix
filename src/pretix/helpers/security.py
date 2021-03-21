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
import hashlib
import time

from django.conf import settings


class SessionInvalid(Exception):
    pass


class SessionReauthRequired(Exception):
    pass


def get_user_agent_hash(request):
    return hashlib.sha256(request.headers['User-Agent'].encode()).hexdigest()


def assert_session_valid(request):
    if not settings.PRETIX_LONG_SESSIONS or not request.session.get('pretix_auth_long_session', False):
        last_used = request.session.get('pretix_auth_last_used', time.time())
        if time.time() - request.session.get('pretix_auth_login_time',
                                             time.time()) > settings.PRETIX_SESSION_TIMEOUT_ABSOLUTE:
            request.session['pretix_auth_login_time'] = 0
            raise SessionInvalid()
        if time.time() - last_used > settings.PRETIX_SESSION_TIMEOUT_RELATIVE:
            raise SessionReauthRequired()

    if 'User-Agent' in request.headers:
        if 'pinned_user_agent' in request.session:
            if request.session.get('pinned_user_agent') != get_user_agent_hash(request):
                raise SessionInvalid()
        else:
            request.session['pinned_user_agent'] = get_user_agent_hash(request)

    request.session['pretix_auth_last_used'] = int(time.time())
    return True
