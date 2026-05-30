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
import re
import typing
import weakref

from celery.exceptions import Retry
from sentry_sdk import Hub
from sentry_sdk.integrations import django as djangosentry
from sentry_sdk.scrubber import EventScrubber
from sentry_sdk.utils import AnnotatedValue, capture_internal_exceptions

if typing.TYPE_CHECKING:
    from sentry_sdk._types import Event


def _make_event_processor(weak_request, integration):
    def event_processor(event, hint):
        request = weak_request()
        if request is None:
            return event

        with capture_internal_exceptions():
            djangosentry._set_user_info(request, event)

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


class PretixEventScrubber(EventScrubber):
    secret_re = re.compile(
        '.*(pretixsecret|ramiiosecret|PRIVATE KEY|://[^/@:]*:[^/@:]+@).*',
        re.IGNORECASE
    )

    def scrub_dict(self, d: object) -> None:
        if not isinstance(d, dict):
            return

        super().scrub_dict(d)
        self._scrub_dict_for_known_secrets(d)

    def _scrub_dict_for_known_secrets(self, d: dict):
        for k, v in d.items():
            if isinstance(v, str) and self.secret_re.match(v):
                d[k] = AnnotatedValue.substituted_because_contains_sensitive_data()

    def scrub_exception(self, event: "Event") -> None:
        with capture_internal_exceptions():
            if "exception" in event:
                self.scrub_dict(event["exception"])

    def scrub_event(self, event: "Event") -> None:
        super().scrub_event(event)
        self.scrub_exception(event)
        print(event)
