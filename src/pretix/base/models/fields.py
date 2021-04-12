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
from django.core import exceptions
from django.db.models import TextField, lookups as builtin_lookups
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

DELIMITER = "\x1F"


class MultiStringField(TextField):
    default_error_messages = {
        'delimiter_found': _('No value can contain the delimiter character.')
    }

    def __init__(self, verbose_name=None, name=None, **kwargs):
        super().__init__(verbose_name, name, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def to_python(self, value):
        if isinstance(value, (list, tuple)):
            return value
        elif value:
            return [v for v in value.split(DELIMITER) if v]
        else:
            return []

    def get_prep_value(self, value):
        if isinstance(value, (list, tuple)):
            return DELIMITER + DELIMITER.join(value) + DELIMITER
        elif value is None:
            return ""
        raise TypeError("Invalid data type passed.")

    def get_prep_lookup(self, lookup_type, value):  # NOQA
        raise TypeError('Lookups on multi strings are currently not supported.')

    def from_db_value(self, value, expression, connection):
        if value:
            return [v for v in value.split(DELIMITER) if v]
        else:
            return []

    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        for l in value:
            if DELIMITER in l:
                raise exceptions.ValidationError(
                    self.error_messages['delimiter_found'],
                    code='delimiter_found',
                )

    def get_lookup(self, lookup_name):
        if lookup_name == 'contains':
            return MultiStringContains
        elif lookup_name == 'icontains':
            return MultiStringIContains
        raise NotImplementedError(
            "Lookup '{}' doesn't work with MultiStringField".format(lookup_name),
        )


class MultiStringContains(builtin_lookups.Contains):
    def process_rhs(self, qn, connection):
        sql, params = super().process_rhs(qn, connection)
        params[0] = "%" + DELIMITER + params[0][1:-1] + DELIMITER + "%"
        return sql, params


class MultiStringIContains(builtin_lookups.IContains):
    def process_rhs(self, qn, connection):
        sql, params = super().process_rhs(qn, connection)
        params[0] = "%" + DELIMITER + params[0][1:-1] + DELIMITER + "%"
        return sql, params


class MultiStringSerializer(serializers.Field):
    def __init__(self, **kwargs):
        self.allow_blank = kwargs.pop('allow_blank', False)
        super().__init__(**kwargs)

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        if isinstance(data, list):
            return data
        else:
            raise ValidationError('Invalid data type.')


serializers.ModelSerializer.serializer_field_mapping[MultiStringField] = MultiStringSerializer
