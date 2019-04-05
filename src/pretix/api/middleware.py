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
                    call.response_body = resp.content.encode() if isinstance(resp.content, str) else resp.content
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

            r = HttpResponse(
                content=call.response_body,
                status=call.response_code,
            )
            for k, v in json.loads(call.response_headers).values():
                r[k] = v
            return r
