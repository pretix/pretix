import contextlib

from django.db import transaction
from django.db.models import Aggregate, Field, Lookup
from django.db.models.expressions import OrderBy


class DummyRollbackException(Exception):
    pass


@contextlib.contextmanager
def rolledback_transaction():
    """
    This context manager runs your code in a database transaction that will be rolled back in the end.
    This can come in handy to simulate the effects of a database operation that you do not actually
    want to perform.

    Note that rollbacks are a very slow operation on most database backends. Also, long-running
    transactions can slow down other operations currently running and you should not use this
    in a place that is called frequently.
    """
    try:
        with transaction.atomic():
            yield
            raise DummyRollbackException()
    except DummyRollbackException:
        pass
    else:
        raise Exception('Invalid state, should have rolled back.')


@contextlib.contextmanager
def casual_reads():
    """
    Kept for backwards compatibility.
    """
    yield


class FixedOrderBy(OrderBy):
    # Workaround for https://code.djangoproject.com/ticket/28848
    template = '%(expression)s %(ordering)s'

    def as_sql(self, compiler, connection, template=None, **extra_context):
        if not template:
            if self.nulls_last:
                template = '%s NULLS LAST' % self.template
            elif self.nulls_first:
                template = '%s NULLS FIRST' % self.template
        connection.ops.check_expression_support(self)
        expression_sql, params = compiler.compile(self.expression)
        placeholders = {
            'expression': expression_sql,
            'ordering': 'DESC' if self.descending else 'ASC',
        }
        placeholders.update(extra_context)
        template = template or self.template
        params = params * template.count('%(expression)s')
        return (template % placeholders).rstrip(), params


class GroupConcat(Aggregate):
    function = 'group_concat'
    template = '%(function)s(%(field)s, "%(separator)s")'

    def __init__(self, *expressions, **extra):
        if 'separator' not in extra:
            # For PostgreSQL separator is an obligatory
            extra.update({'separator': ','})
        super().__init__(*expressions, **extra)

    def as_postgresql(self, compiler, connection):
        return super().as_sql(
            compiler, connection,
            function='string_agg',
            template="%(function)s(%(field)s::text, '%(separator)s')",
        )


class ReplicaRouter:

    def db_for_read(self, model, **hints):
        return 'default'

    def db_for_write(self, model, **hints):
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        db_list = ('default', 'replica')
        if obj1._state.db in db_list and obj2._state.db in db_list:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hintrs):
        return True


@Field.register_lookup
class NotEqual(Lookup):
    lookup_name = 'ne'

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params
        return '%s <> %s' % (lhs, rhs), params
