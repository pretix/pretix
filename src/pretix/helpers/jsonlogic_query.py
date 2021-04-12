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
from datetime import timedelta

from django.db.models import Func, Value

logger = logging.getLogger(__name__)


class Equal(Func):
    arg_joiner = ' = '
    arity = 2
    function = ''


class GreaterThan(Func):
    arg_joiner = ' > '
    arity = 2
    function = ''


class GreaterEqualThan(Func):
    arg_joiner = ' >= '
    arity = 2
    function = ''


class LowerEqualThan(Func):
    arg_joiner = ' < '
    arity = 2
    function = ''


class LowerThan(Func):
    arg_joiner = ' < '
    arity = 2
    function = ''


class InList(Func):
    arity = 2

    def as_sql(self, compiler, connection, function=None, template=None, arg_joiner=None, **extra_context):
        connection.ops.check_expression_support(self)

        # This ignores the special case for databases which limit the number of
        # elements which can appear in an 'IN' clause, which hopefully is only Oracle.
        lhs, lhs_params = compiler.compile(self.source_expressions[0])

        if not isinstance(self.source_expressions[1], Value) and not isinstance(self.source_expressions[1].value, (list, tuple)):
            raise TypeError(f'Dynamic right-hand-site currently not implemented, found {type(self.source_expressions[1])}')
        rhs, rhs_params = ['%s' for _ in self.source_expressions[1].value], [d for d in self.source_expressions[1].value]

        return '%s IN (%s)' % (lhs, ', '.join(rhs)), lhs_params + rhs_params


def tolerance(b, tol=None, sign=1):
    if tol:
        return b + timedelta(minutes=sign * float(tol))
    return b
