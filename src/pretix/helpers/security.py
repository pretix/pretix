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
from django.contrib.gis.geoip2 import GeoIP2
from django.core.cache import cache
from geoip2.errors import AddressNotFoundError

from pretix.helpers.http import get_client_ip


class SessionInvalid(Exception):
    pass


class SessionReauthRequired(Exception):
    pass


def get_user_agent_hash(request):
    return hashlib.sha256(request.headers['User-Agent'].encode()).hexdigest()


_geoip = None


def _get_country(request):
    global _geoip

    if not _geoip:
        _geoip = GeoIP2()

    try:
        res = _geoip.country(get_client_ip(request))
    except AddressNotFoundError:
        return None
    return res['country_code']


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

    if settings.HAS_GEOIP:
        client_ip = get_client_ip(request)
        hashed_client_ip = hashlib.sha256(client_ip.encode()).hexdigest()
        country = cache.get_or_set(f'geoip_country_{hashed_client_ip}', lambda: _get_country(request), timeout=300)

        if 'pinned_country' in request.session:
            if request.session.get('pinned_country') != country:
                raise SessionInvalid()
        else:
            request.session['pinned_country'] = country

    request.session['pretix_auth_last_used'] = int(time.time())
    return True
