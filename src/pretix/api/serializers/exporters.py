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
from django.conf import settings
from django.http import QueryDict
from pytz import common_timezones
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.forms import form_field_to_serializer_field
from pretix.base.exporter import OrganizerLevelExportMixin
from pretix.base.models import ScheduledEventExport, ScheduledOrganizerExport
from pretix.base.timeframes import SerializerDateFrameField


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


class JobRunSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        ex = kwargs.pop('exporter')
        events = kwargs.pop('events', None)
        super().__init__(*args, **kwargs)
        if events is not None and not isinstance(ex, OrganizerLevelExportMixin):
            self.fields["events"] = serializers.SlugRelatedField(
                queryset=events,
                required=False,
                allow_empty=False,
                slug_field='slug',
                many=True
            )
        for k, v in ex.export_form_fields.items():
            self.fields[k] = form_field_to_serializer_field(v)

    def to_internal_value(self, data):
        if isinstance(data, QueryDict):
            data = data.copy()

        for k, v in self.fields.items():
            if isinstance(v, serializers.ManyRelatedField) and k not in data and k != "events":
                data[k] = []

        for fk in self.fields.keys():
            # Backwards compatibility for exports that used to take e.g. (date_from, date_to) or (event_date_from, event_date_to)
            # and now only take date_range.
            if fk.endswith("_range") and isinstance(self.fields[fk], SerializerDateFrameField) and fk not in data:
                if fk.replace("_range", "_from") in data:
                    d_from = data.pop(fk.replace("_range", "_from"))
                    if d_from:
                        d_from = serializers.DateField().to_internal_value(d_from)
                else:
                    d_from = None
                if fk.replace("_range", "_to") in data:
                    d_to = data.pop(fk.replace("_range", "_to"))
                    if d_to:
                        d_to = serializers.DateField().to_internal_value(d_to)
                else:
                    d_to = None
                data[fk] = f'{d_from.isoformat() if d_from else ""}/{d_to.isoformat() if d_to else ""}'

        data = super().to_internal_value(data)
        return data

    def is_valid(self, raise_exception=False):
        super().is_valid(raise_exception=raise_exception)

        fields_keys = set(self.fields.keys())
        input_keys = set(self.initial_data.keys())

        additional_fields = input_keys - fields_keys

        if bool(additional_fields):
            self._errors['fields'] = ['Additional fields not allowed: {}.'.format(list(additional_fields))]

        if self._errors and raise_exception:
            raise ValidationError(self.errors)

        return not bool(self._errors)


class ScheduledExportSerializer(serializers.ModelSerializer):
    schedule_next_run = serializers.DateTimeField(read_only=True)
    export_identifier = serializers.ChoiceField(choices=[])
    locale = serializers.ChoiceField(choices=settings.LANGUAGES, default='en')
    owner = serializers.SlugRelatedField(slug_field='email', read_only=True)
    error_counter = serializers.IntegerField(read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['export_identifier'].choices = [(e, e) for e in self.context['exporters']]

    def validate(self, attrs):
        if attrs.get("export_form_data"):
            identifier = attrs.get('export_identifier', self.instance.export_identifier if self.instance else None)
            exporter = self.context['exporters'].get(identifier)
            if exporter:
                try:
                    JobRunSerializer(exporter=exporter).to_internal_value(attrs["export_form_data"])
                except ValidationError as e:
                    raise ValidationError({"export_form_data": e.detail})
            else:
                raise ValidationError({"export_identifier": ["Unknown exporter."]})
        return attrs

    def validate_mail_additional_recipients(self, value):
        d = value.replace(' ', '')
        if len(d.split(',')) > 25:
            raise ValidationError('Please enter less than 25 recipients.')
        return d

    def validate_mail_additional_recipients_cc(self, value):
        d = value.replace(' ', '')
        if len(d.split(',')) > 25:
            raise ValidationError('Please enter less than 25 recipients.')
        return d

    def validate_mail_additional_recipients_bcc(self, value):
        d = value.replace(' ', '')
        if len(d.split(',')) > 25:
            raise ValidationError('Please enter less than 25 recipients.')
        return d


class ScheduledEventExportSerializer(ScheduledExportSerializer):

    class Meta:
        model = ScheduledEventExport
        fields = [
            'id',
            'owner',
            'export_identifier',
            'export_form_data',
            'locale',
            'mail_additional_recipients',
            'mail_additional_recipients_cc',
            'mail_additional_recipients_bcc',
            'mail_subject',
            'mail_template',
            'schedule_rrule',
            'schedule_rrule_time',
            'schedule_next_run',
            'error_counter',
        ]


class ScheduledOrganizerExportSerializer(ScheduledExportSerializer):
    timezone = serializers.ChoiceField(default=settings.TIME_ZONE, choices=[(a, a) for a in common_timezones])

    class Meta:
        model = ScheduledOrganizerExport
        fields = [
            'id',
            'owner',
            'export_identifier',
            'export_form_data',
            'locale',
            'mail_additional_recipients',
            'mail_additional_recipients_cc',
            'mail_additional_recipients_bcc',
            'mail_subject',
            'mail_template',
            'schedule_rrule',
            'schedule_rrule_time',
            'schedule_next_run',
            'timezone',
            'error_counter',
        ]
