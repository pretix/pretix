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
from django.http import HttpResponse, JsonResponse
from rest_framework import status
from rest_framework.views import APIView

from pretix.api.models import ApiCall

logger = logging.getLogger(__name__)


class IdempotencyQueryView(APIView):
    # Experimental feature, therefore undocumented for now
    authentication_classes = ()
    permission_classes = ()

    def get(self, request, format=None):
        idempotency_key = request.GET.get("key")
        auth_hash_parts = '{}:{}'.format(
            request.headers.get('Authorization', ''),
            request.COOKIES.get(settings.SESSION_COOKIE_NAME, '')
        )
        auth_hash = sha1(auth_hash_parts.encode()).hexdigest()
        if not idempotency_key:
            return JsonResponse({
                'detail': 'No idempotency key given.'
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            call = ApiCall.objects.get(
                auth_hash=auth_hash,
                idempotency_key=idempotency_key,
            )
        except ApiCall.DoesNotExist:
            return JsonResponse({
                'detail': 'Idempotency key not seen before.'
            }, status=status.HTTP_404_NOT_FOUND)

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
