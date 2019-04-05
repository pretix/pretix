import json
from hashlib import sha1

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.timezone import now
from rest_framework import status

from pretix.api.models import ApiCall


class IdempotencyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return self.get_response(request)

        if not request.path.startswith('/api/'):
            return self.get_response(request)

        if not request.META.get('HTTP_X_IDEMPOTENCY_KEY'):
            return self.get_response(request)

        auth_hash_parts = '{}:{}'.format(
            request.META.get('HTTP_AUTHORIZATION', ''),
            request.COOKIES.get(settings.SESSION_COOKIE_NAME, '')
        )
        auth_hash = sha1(auth_hash_parts.encode()).hexdigest()
        idempotency_key = request.META.get('HTTP_X_IDEMPOTENCY_KEY', '')

        with transaction.atomic():
            call, created = ApiCall.objects.select_for_update().get_or_create(
                auth_hash=auth_hash,
                idempotency_key=idempotency_key,
                defaults={
                    'locked': now(),
                    'request_method': request.method,
                    'request_path': request.path,
                    'response_code': 0,
                    'response_headers': '{}',
                    'response_body': b''
                }
            )

        if created:
            resp = self.get_response(request)
            with transaction.atomic():
                if resp.status_code in (409, 429, 503):
                    # This is the exception: These calls are *meant* to be retried!
                    call.delete()
                else:
                    call.response_code = resp.status_code
                    if isinstance(resp.content, str):
                        call.response_body = resp.content.encode()
                    elif isinstance(resp.content, memoryview):
                        call.response_body = resp.content.tobytes()
                    elif isinstance(resp.content, bytes):
                        call.response_body = resp.content
                    elif hasattr(resp.content, 'read'):
                        call.response_body = resp.read()
                    elif hasattr(resp, 'data'):
                        call.response_body = json.dumps(resp.data)
                    else:
                        call.response_body = repr(resp).encode()
                    call.response_headers = json.dumps(resp._headers)
                    call.locked = None
                    call.save(update_fields=['locked', 'response_code', 'response_headers',
                                             'response_body'])
            return resp
        else:
            if call.locked:
                r = JsonResponse(
                    {'detail': 'Concurrent request with idempotency key.'},
                    status=status.HTTP_409_CONFLICT,
                )
                r['Retry-After'] = 5
                return r

            content = call.response_body
            if isinstance(content, memoryview):
                content = content.tobytes()
            r = HttpResponse(
                content=content,
                status=call.response_code,
            )
            for k, v in json.loads(call.response_headers).values():
                r[k] = v
            return r
