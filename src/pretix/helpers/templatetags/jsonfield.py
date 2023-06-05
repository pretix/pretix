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
import copy

from django.db import NotSupportedError
from django.db.models import Expression, JSONField


def postgres_compile_json_path(key_transforms):
    return "{" + ','.join(key_transforms) + "}"


def sqlite_compile_json_path(key_transforms):
    path = ['$']
    for key_transform in key_transforms:
        try:
            num = int(key_transform)
            path.append('[{}]'.format(num))
        except ValueError:  # non-integer
            path.append('.')
            path.append(key_transform)
    return ''.join(path)


class JSONExtract(Expression):
    def __init__(self, expression, *path, output_field=JSONField(), **extra):
        super().__init__(output_field=output_field)
        self.path = path
        self.source_expression = self._parse_expressions(expression)[0]
        self.extra = extra

    def resolve_expression(self, query=None, allow_joins=True, reuse=None, summarize=False, for_save=False):
        c = self.copy()
        c.is_summary = summarize
        c.source_expression = c.source_expression.resolve_expression(query, allow_joins, reuse, summarize, for_save)
        return c

    def as_sql(self, compiler, connection, function=None, template=None, arg_joiner=None, **extra_context):
        if '.postgresql' in connection.settings_dict['ENGINE']:
            params = []
            arg_sql, arg_params = compiler.compile(self.source_expression)
            params.extend(arg_params)
            json_path = postgres_compile_json_path(self.path)
            params.append(json_path)
            template = '{} #> %s'.format(arg_sql)
            return template, params
        elif '.sqlite' in connection.settings_dict['ENGINE']:
            params = []
            arg_sql, arg_params = compiler.compile(self.source_expression)
            params.extend(arg_params)
            json_path = sqlite_compile_json_path(self.path)
            params.append(json_path)
            template = 'json_extract({}, %s)'.format(arg_sql)
            return template, params
        else:
            raise NotSupportedError(
                'Functions on JSONFields are only supported on SQLite and PostgreSQL at the moment.'
            )

    def copy(self):
        c = super().copy()
        c.source_expression = copy.copy(self.source_expression)
        c.extra = self.extra.copy()
        return c
