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
