import re
import weakref
from collections import OrderedDict

from sentry_sdk import Hub
from sentry_sdk.integrations.django import DjangoIntegration, _set_user_info
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
            _set_user_info(request, event)
            request_info = event.setdefault("request", {})
            request_info["cookies"] = dict(request.COOKIES)

        scrub_data(event.get("request", {}))
        if 'exception' in event:
            exc = event.get("exception", {})
            for val in exc.get('values', []):
                stack = val.get('stacktrace', {})
                for frame in stack.get('frames', []):
                    scrub_data(frame['vars'])
        return event

    return event_processor


class PretixSentryIntegration(DjangoIntegration):
    @staticmethod
    def setup_once():
        DjangoIntegration.setup_once()
        from django.core.handlers.base import BaseHandler

        old_get_response = BaseHandler.get_response

        def sentry_patched_get_response(self, request):
            hub = Hub.current
            integration = hub.get_integration(DjangoIntegration)
            if integration is not None:
                with hub.configure_scope() as scope:
                    scope.add_event_processor(
                        _make_event_processor(weakref.ref(request), integration)
                    )
            return old_get_response(self, request)

        BaseHandler.get_response = sentry_patched_get_response
