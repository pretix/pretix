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
import time

from django.urls import resolve

from pretix.base.metrics import pretix_view_duration_seconds


class MetricsMiddleware(object):
    banlist = (
        '/healthcheck/',
        '/jsi18n/',
        '/metrics',
    )

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        for b in self.banlist:
            if b in request.path:
                return self.get_response(request)

        url = resolve(request.path_info)

        t0 = time.perf_counter()
        resp = self.get_response(request)
        tdiff = time.perf_counter() - t0
        pretix_view_duration_seconds.observe(tdiff, status_code=resp.status_code, method=request.method,
                                             url_name=url.namespace + ':' + url.url_name)

        return resp
