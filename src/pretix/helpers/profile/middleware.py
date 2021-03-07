#
# This file is part of pretix Community.
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
# ADDITIONAL TERMS: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are applicable
# granting you additional permissions and placing additional restrictions on your usage of this software. Please refer
# to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive this file, see
# <https://pretix.eu/about/en/license>.
#
import cProfile
import os
import random
import time

from django.conf import settings


class CProfileMiddleware(object):
    banlist = (
        '/healthcheck/',
        '/jsi18n/'
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

        if settings.PROFILING_RATE > 0 and random.random() < settings.PROFILING_RATE / 100:
            profiler = cProfile.Profile()
            profiler.enable()
            starttime = time.perf_counter()
            response = self.get_response(request)
            profiler.disable()
            tottime = time.perf_counter() - starttime
            profiler.dump_stats(os.path.join(settings.PROFILE_DIR, '{time:.0f}_{tottime:.3f}_{path}.pstat'.format(
                path=request.path[1:].replace("/", "_"), tottime=tottime, time=time.time()
            )))
            return response
        else:
            return self.get_response(request)
