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
import contextvars

from django.conf import settings
from django.db import connection

debugflags_var = contextvars.ContextVar('debugflags', default=frozenset())


class DebugFlagMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if '_debug_flag' in request.GET:
            debugflags_var.set(frozenset(request.GET.getlist('_debug_flag')))
        else:
            debugflags_var.set(frozenset())

        if 'skip-csrf' in debugflags_var.get():
            request.csrf_processing_done = True

        if 'repeatable-read' in debugflags_var.get():
            with connection.cursor() as cursor:
                if 'postgresql' in settings.DATABASES['default']['ENGINE']:
                    cursor.execute('SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL REPEATABLE READ;')
                elif 'mysql' in settings.DATABASES['default']['ENGINE']:
                    cursor.execute('SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;')

        try:
            return self.get_response(request)
        finally:
            if 'repeatable-read' in debugflags_var.get():
                with connection.cursor() as cursor:
                    if 'postgresql' in settings.DATABASES['default']['ENGINE']:
                        cursor.execute('SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL READ COMMITTED;')
                    elif 'mysql' in settings.DATABASES['default']['ENGINE']:
                        cursor.execute('SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;')
