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
import contextlib

from django.core.exceptions import FieldDoesNotExist
from django.db import connection, transaction
from django.db.models import (
    Aggregate, Expression, F, Field, Lookup, OrderBy, Value,
)
from django.utils.functional import lazy


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


class PostgresWindowFrame(Expression):
    template = "%(frame_type)s BETWEEN %(start)s AND %(end)s"

    def __init__(self, frame_type=None, start=None, end=None):
        self.frame_type = frame_type
        self.start = Value(start)
        self.end = Value(end)

    def set_source_expressions(self, exprs):
        self.start, self.end = exprs

    def get_source_expressions(self):
        return [self.start, self.end]

    def as_sql(self, compiler, connection):
        return (
            self.template
            % {
                "frame_type": self.frame_type,
                "start": self.start.value,
                "end": self.end.value,
            },
            [],
        )

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self)

    def get_group_by_cols(self, alias=None):
        return []

    def __str__(self):
        return self.template % {
            "frame_type": self.frame_type,
            "start": self.start.value,
            "end": self.end.value,
        }


# This is a short-hand for .select_for_update(of=("self,")), that falls back gracefully on databases that don't support
# the SELECT FOR UPDATE OF ... query.
OF_SELF = lazy(lambda: ("self",) if connection.features.has_select_for_update_of else (), tuple)()


def get_deterministic_ordering(model, ordering):
    """
    Ensure a deterministic order across all database backends. Search for a
    single field or unique together set of fields providing a total
    ordering. If these are missing, augment the ordering with a descendant
    primary key.

    This has mostly been vendored from
    https://github.com/django/django/blob/d8e1442ce2c56282785dd806e5c1147975e8c857/django/contrib/admin/views/main.py#L390
    """
    if isinstance(ordering, str):
        ordering = (ordering,)
    ordering = list(ordering)
    ordering_fields = set()
    total_ordering_fields = {"pk"} | {
        field.attname
        for field in model._meta.fields
        if field.unique and not field.null
    }
    for part in ordering:
        # Search for single field providing a total ordering.
        field_name = None
        if isinstance(part, str):
            field_name = part.lstrip("-")
        elif isinstance(part, F):
            field_name = part.name
        elif isinstance(part, OrderBy) and isinstance(part.expression, F):
            field_name = part.expression.name
        if field_name:
            # Normalize attname references by using get_field().
            try:
                field = model._meta.get_field(field_name)
            except FieldDoesNotExist:
                # Could be "?" for random ordering or a related field
                # lookup. Skip this part of introspection for now.
                continue
            # Ordering by a related field name orders by the referenced
            # model's ordering. Skip this part of introspection for now.
            if field.remote_field and field_name == field.name:
                continue
            if field.attname in total_ordering_fields:
                break
            ordering_fields.add(field.attname)
    else:
        # No single total ordering field, try unique_together and total
        # unique constraints.
        constraint_field_names = (
            *model._meta.unique_together,
            *(
                constraint.fields
                for constraint in model._meta.total_unique_constraints
            ),
        )
        for field_names in constraint_field_names:
            # Normalize attname references by using get_field().
            fields = [
                model._meta.get_field(field_name) for field_name in field_names
            ]
            # Composite unique constraints containing a nullable column
            # cannot ensure total ordering.
            if any(field.null for field in fields):
                continue
            if ordering_fields.issuperset(field.attname for field in fields):
                break
        else:
            # If no set of unique fields is present in the ordering, rely
            # on the primary key to provide total ordering.
            ordering.append("-pk")
    return ordering
