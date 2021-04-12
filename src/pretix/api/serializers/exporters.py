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
from django import forms
from django.http import QueryDict
from rest_framework import serializers


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
    (forms.NullBooleanField, serializers.NullBooleanField, ()),
    (forms.BooleanField, serializers.BooleanField, ()),
)


class SerializerDescriptionField(serializers.Field):
    def to_representation(self, value):
        fields = []
        for k, v in value.fields.items():
            d = {
                'name': k,
                'required': v.required,
            }
            if isinstance(v, serializers.ChoiceField):
                d['choices'] = list(v.choices.keys())
            fields.append(d)

        return fields


class ExporterSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    verbose_name = serializers.CharField()
    input_parameters = SerializerDescriptionField(source='_serializer')


class PrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    def to_representation(self, value):
        if isinstance(value, int):
            return value
        return super().to_representation(value)


class JobRunSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        ex = kwargs.pop('exporter')
        events = kwargs.pop('events', None)
        super().__init__(*args, **kwargs)
        if events is not None:
            self.fields["events"] = serializers.SlugRelatedField(
                queryset=events,
                required=True,
                allow_empty=False,
                slug_field='slug',
                many=True
            )
        for k, v in ex.export_form_fields.items():
            for m_from, m_to, m_kwargs in simple_mappings:
                if isinstance(v, m_from):
                    self.fields[k] = m_to(
                        required=v.required,
                        allow_null=not v.required,
                        validators=v.validators,
                        **{kwarg: getattr(v, kwargs, None) for kwarg in m_kwargs}
                    )
                    break

            if isinstance(v, forms.ModelMultipleChoiceField):
                self.fields[k] = PrimaryKeyRelatedField(
                    queryset=v.queryset,
                    required=v.required,
                    allow_empty=not v.required,
                    validators=v.validators,
                    many=True
                )
            elif isinstance(v, forms.ModelChoiceField):
                self.fields[k] = PrimaryKeyRelatedField(
                    queryset=v.queryset,
                    required=v.required,
                    allow_null=not v.required,
                    validators=v.validators,
                )
            elif isinstance(v, forms.MultipleChoiceField):
                self.fields[k] = serializers.MultipleChoiceField(
                    choices=v.choices,
                    required=v.required,
                    allow_empty=not v.required,
                    validators=v.validators,
                )
            elif isinstance(v, forms.ChoiceField):
                self.fields[k] = serializers.ChoiceField(
                    choices=v.choices,
                    required=v.required,
                    allow_null=not v.required,
                    validators=v.validators,
                )
            else:
                self.fields[k] = FormFieldWrapperField(form_field=v, required=v.required, allow_null=not v.required)

    def to_internal_value(self, data):
        if isinstance(data, QueryDict):
            data = data.copy()
        for k, v in self.fields.items():
            if isinstance(v, serializers.ManyRelatedField) and k not in data:
                data[k] = []
        data = super().to_internal_value(data)
        return data
