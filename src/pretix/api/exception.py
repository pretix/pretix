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

import ujson
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler, status

from pretix.base.services.locking import LockTimeoutException

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if isinstance(exc, LockTimeoutException):
        response = Response(
            {'detail': 'The server was too busy to process your request. Please try again.'},
            status=status.HTTP_409_CONFLICT,
            headers={
                'Retry-After': 5
            }
        )

    if isinstance(exc, exceptions.APIException):
        logger.info(f'API Exception [{exc.status_code}]: {ujson.dumps(exc.detail)}')

    return response
