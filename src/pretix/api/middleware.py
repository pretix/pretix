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
import json
import logging
from hashlib import sha1

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import resolve
from django.utils.timezone import now
from django_scopes import scope
from rest_framework import status

from pretix.api.models import ApiCall
from pretix.base.models import Organizer
from pretix.helpers import OF_SELF

logger = logging.getLogger(__name__)


class IdempotencyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return self.get_response(request)

        if not request.path.startswith('/api/'):
            return self.get_response(request)

        if not request.headers.get('X-Idempotency-Key'):
            return self.get_response(request)

        auth_hash_parts = '{}:{}'.format(
            request.headers.get('Authorization', ''),
            request.COOKIES.get(settings.SESSION_COOKIE_NAME, '')
        )
        auth_hash = sha1(auth_hash_parts.encode()).hexdigest()
        idempotency_key = request.headers.get('X-Idempotency-Key', '')

        with transaction.atomic(durable=True):
            call, created = ApiCall.objects.select_for_update(of=OF_SELF).get_or_create(
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
            with transaction.atomic(durable=True):
                if resp.status_code in (409, 429, 500, 503):
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
                    call.response_headers = json.dumps(resp.headers._store)
                    call.locked = None
                    call.save(update_fields=['locked', 'response_code', 'response_headers',
                                             'response_body'])
            return resp
        else:
            if call.locked:
                logger.info(
                    f'Concurrent request with idempotency key {idempotency_key} blocked.'
                )
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
            logger.info(f'API response replayed from idempotency store for key {idempotency_key} [{call.response_code}]')
            for k, v in json.loads(call.response_headers).values():
                r[k] = v
            return r


class ApiScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        url = resolve(request.path_info)
        if 'organizer' in url.kwargs:
            request.organizer = Organizer.objects.filter(
                slug=url.kwargs['organizer'],
            ).first()

        with scope(organizer=getattr(request, 'organizer', None)):
            return self.get_response(request)
