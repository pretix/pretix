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
from django.conf import settings
from django.core import cache
from django.http import HttpResponse

from ..models import User


def healthcheck(request):
    # Perform a simple DB query to see that DB access works
    User.objects.exists()

    # Test if redis access works
    if settings.HAS_REDIS:
        import django_redis

        redis = django_redis.get_redis_connection("redis")
        redis.set("_healthcheck", 1)
        if not redis.exists("_healthcheck"):
            return HttpResponse("Redis not available.", status=503)

    cache.cache.set("_healthcheck", "1")
    if not cache.cache.get("_healthcheck") == "1":
        return HttpResponse("Cache not available.", status=503)

    return HttpResponse()
