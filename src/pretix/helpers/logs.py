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
import logging

from django.core.signals import request_finished
from django.dispatch import receiver

try:
    from asgiref.local import Local
except ImportError:
    from threading import local as Local

from django.conf import settings


class AdminExistsFilter(logging.Filter):
    def filter(self, record):
        return not settings.DEBUG and len(settings.ADMINS) > 0


local = Local()


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = getattr(local, 'request_id', None)
        return True


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.REQUEST_ID_HEADER and settings.REQUEST_ID_HEADER in request.headers:
            local.request_id = request.request_id = request.headers[settings.REQUEST_ID_HEADER]

            if settings.SENTRY_ENABLED:
                import sentry_sdk
                sentry_sdk.set_tag("request_id", request.request_id)
        else:
            local.request_id = request.request_id = None

        return self.get_response(request)


@receiver(request_finished)
def on_request_finished(sender, **kwargs):
    # not part of middleware, since things could be logged after the middleware stack is finished
    local.request_id = None
