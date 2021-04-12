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

from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger('pretix.security.csp')


@csrf_exempt
def csp_report(request):
    try:
        body = json.loads(request.body.decode())
        logger.warning(
            'CSP violation at {r[document-uri]}\n'
            'Referer: {r[referrer]}\n'
            'Blocked: {r[blocked-uri]}\n'
            'Violated: {r[violated-directive]}\n'
            'Original polity: {r[original-policy]}'.format(r=body['csp-report'])
        )
    except (ValueError, KeyError) as e:
        logger.exception('CSP report failed ' + str(e))
        return HttpResponseBadRequest()
    return HttpResponse()
