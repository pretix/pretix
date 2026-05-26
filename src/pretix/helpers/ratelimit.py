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
import hashlib
import ipaddress
import logging

from django.conf import settings
from django.http import HttpRequest

from pretix.helpers.http import get_client_ip

logger = logging.getLogger(__name__)


def _get_key(key, parameters):
    return f'pretix:ratelimit:{key}:' + hashlib.sha256(','.join(str(p) for p in parameters).encode()).hexdigest()


def _get_ip(request):
    if not settings.HAS_REDIS:
        return None
    client_ip = get_client_ip(request)
    if not client_ip:
        return None
    try:
        client_ip = ipaddress.ip_address(client_ip)
    except ValueError:
        # Web server not set up correctly
        return None
    if client_ip.is_private:
        # This is the private IP of the server, web server not set up correctly
        return None
    return str(client_ip)


def rate_limit(key: str, *parameters, include_ip_from_request: HttpRequest=None, max_num: int, expire_time: int):
    """
    This is a shared utility to implement simple rate limiting in operations like
    password resets. This is by far no perfect implementation of rate limiting, as
    it the window is prolonge

    :param key: The key refering to the feature like "pwreset"
    :param parameters: Any number of things to be hashed as the bucket key
    :param max_num: The maximum number of actions to performed within expire_time of the first action
    :param expire_time: The length of the time window in seconds
    :return:
    """
    if not settings.HAS_REDIS:
        # No rate limiting
        return False

    from django_redis import get_redis_connection
    rc = get_redis_connection("redis")

    if include_ip_from_request:
        ip = _get_ip(include_ip_from_request)
        if not ip:
            # IP not discovered, can't rate limit
            return False
        parameters = (*parameters, ip)

    redis_key = _get_key(key, parameters)
    p = rc.pipeline()
    p.set(redis_key, 0, nx=True, ex=expire_time)  # Start a rate limit window if none is running
    p.incr(redis_key)
    new_counter = p.execute()[1]

    if new_counter > max_num:
        return True

    return False


def rate_limit_reset(key: str, *parameters, include_ip_from_request: HttpRequest=None):
    """
    Reset a rate limit bucket.
    """
    if not settings.HAS_REDIS:
        # No rate limiting
        return

    from django_redis import get_redis_connection
    rc = get_redis_connection("redis")

    if include_ip_from_request:
        ip = _get_ip(include_ip_from_request)
        if not ip:
            # IP not discovered, can't rate limit
            return False
        parameters = (*parameters, ip)

    redis_key = _get_key(key, parameters)
    rc.delete(redis_key)
