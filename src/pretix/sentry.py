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
import re
import weakref
from collections import OrderedDict

from celery.exceptions import Retry
from sentry_sdk import Hub
from sentry_sdk.integrations import django as djangosentry
from sentry_sdk.utils import capture_internal_exceptions

MASK = '*' * 8
KEYS = frozenset([
    'password',
    'secret',
    'passwd',
    'authorization',
    'api_key',
    'apikey',
    'sentry_dsn',
    'access_token',
    'session',
])
VALUES_RE = re.compile(r'^(?:\d[ -]*?){13,16}$')


def scrub_data(data):
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(k, bytes):
                key = k.decode('utf-8', 'replace')
            else:
                key = k
            key = key.lower()
            data[k] = scrub_data(v)
            for blk in KEYS:
                if blk in key:
                    data[k] = MASK
    elif isinstance(data, list):
        for i, l in enumerate(list(data)):
            data[i] = scrub_data(l)
    elif isinstance(data, str):
        if '=' in data:
            # at this point we've assumed it's a standard HTTP query
            # or cookie
            if '&' in data:
                delimiter = '&'
            else:
                delimiter = ';'

            qd = scrub_data(OrderedDict(e.split('=', 1) if '=' in e else (e, None) for e in data.split(delimiter)))
            return delimiter.join((k + '=' + v if v is not None else k) for k, v in qd.items())
        if VALUES_RE.match(data):
            return MASK
    return data


def _make_event_processor(weak_request, integration):
    def event_processor(event, hint):
        request = weak_request()
        if request is None:
            return event

        with capture_internal_exceptions():
            djangosentry._set_user_info(request, event)
            request_info = event.setdefault("request", {})
            request_info["cookies"] = dict(request.COOKIES)

        # Sentry's DjangoIntegration already sets the transaction, but it gets confused by our multi-domain stuff
        # where the URL resolver changes in the middleware stack. Additionally, we'd like to get the method.
        url = djangosentry.LEGACY_RESOLVER.resolve(request.path_info, getattr(request, "urlconf", None))
        if hasattr(request, 'event_domain'):
            url = '/{organizer}/{event}' + url
        elif hasattr(request, 'organizer_domain'):
            url = '/{organizer}' + url
        event['transaction'] = '{} {}'.format(
            request.method,
            url
        )

        # We want to scrub data not only from the request, but from traceback frames as well!
        scrub_data(event.get("request", {}))
        if 'exception' in event:
            exc = event.get("exception", {})
            for val in exc.get('values', []):
                stack = val.get('stacktrace', {})
                for frame in stack.get('frames', []):
                    scrub_data(frame['vars'])
        return event

    return event_processor


class PretixSentryIntegration(djangosentry.DjangoIntegration):

    @staticmethod
    def setup_once():
        djangosentry.DjangoIntegration.setup_once()
        from django.core.handlers.base import BaseHandler

        # DjangoIntegration already patched get_response, we patch it again to add our custom
        # processor

        old_get_response = BaseHandler.get_response

        def sentry_patched_get_response(self, request):
            hub = Hub.current
            integration = hub.get_integration(djangosentry.DjangoIntegration)
            if integration is not None:
                with hub.configure_scope() as scope:
                    scope.add_event_processor(
                        _make_event_processor(weakref.ref(request), integration)
                    )

            return old_get_response(self, request)

        BaseHandler.get_response = sentry_patched_get_response

        if hasattr(BaseHandler, "get_response_async"):
            from sentry_sdk.integrations.django.asgi import (
                patch_get_response_async,
            )

            patch_get_response_async(BaseHandler, djangosentry._before_get_response)


def ignore_retry(event, hint):
    with capture_internal_exceptions():
        if isinstance(hint["exc_info"][1], Retry):
            return None
    return event


def setup_custom_filters():
    hub = Hub.current
    with hub.configure_scope() as scope:
        scope.add_event_processor(ignore_retry)
