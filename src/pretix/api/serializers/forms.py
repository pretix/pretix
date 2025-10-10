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
from django import forms
from rest_framework import serializers

from pretix.base.timeframes import DateFrameField, SerializerDateFrameField

simple_mappings = (
    (forms.DateField, serializers.DateField, ()),
    (forms.TimeField, serializers.TimeField, ()),
    (forms.SplitDateTimeField, serializers.DateTimeField, ()),
    (forms.DateTimeField, serializers.DateTimeField, ()),
    (forms.DecimalField, serializers.DecimalField, ('max_digits', 'decimal_places', 'min_value', 'max_value')),
    (forms.FloatField, serializers.FloatField, ()),
    (forms.IntegerField, serializers.IntegerField, ()),
    (forms.EmailField, serializers.EmailField, ()),
    (forms.UUIDField, serializers.UUIDField, ()),
    (forms.URLField, serializers.URLField, ()),
    (forms.BooleanField, serializers.BooleanField, ()),
)


class PrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    def to_representation(self, value):
        if isinstance(value, int):
            return value
        return super().to_representation(value)


class FormFieldWrapperField(serializers.Field):
    def __init__(self, *args, **kwargs):
        self.form_field = kwargs.pop('form_field')
        super().__init__(*args, **kwargs)

    def to_representation(self, value):
        return self.form_field.widget.format_value(value)

    def to_internal_value(self, data):
        d = self.form_field.widget.value_from_datadict({'name': data}, {}, 'name')
        d = self.form_field.clean(d)
        return d


def form_field_to_serializer_field(field):
    for m_from, m_to, m_kwargs in simple_mappings:
        if isinstance(field, m_from):
            return m_to(
                required=field.required,
                allow_null=not field.required,
                validators=field.validators,
                **{kwarg: getattr(field, kwarg, None) for kwarg in m_kwargs}
            )

    if isinstance(field, forms.NullBooleanField):
        return serializers.BooleanField(
            required=field.required,
            allow_null=True,
            validators=field.validators,
        )
    if isinstance(field, forms.ModelMultipleChoiceField):
        return PrimaryKeyRelatedField(
            queryset=field.queryset,
            required=field.required,
            allow_empty=not field.required,
            validators=field.validators,
            many=True
        )
    elif isinstance(field, forms.ModelChoiceField):
        return PrimaryKeyRelatedField(
            queryset=field.queryset,
            required=field.required,
            allow_null=not field.required,
            validators=field.validators,
        )
    elif isinstance(field, forms.MultipleChoiceField):
        return serializers.MultipleChoiceField(
            choices=field.choices,
            required=field.required,
            allow_empty=not field.required,
            validators=field.validators,
        )
    elif isinstance(field, forms.ChoiceField):
        return serializers.ChoiceField(
            choices=field.choices,
            required=field.required,
            allow_null=not field.required,
            validators=field.validators,
        )
    elif isinstance(field, DateFrameField):
        return SerializerDateFrameField(
            required=field.required,
            allow_null=not field.required,
            validators=field.validators,
        )
    else:
        return FormFieldWrapperField(form_field=field, required=field.required, allow_null=not field.required)
