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
import datetime
from collections import namedtuple
from typing import Union
from zoneinfo import ZoneInfo

from dateutil import parser
from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.formats import get_format
from django.utils.functional import lazy
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

BASE_CHOICES = (
    ('date_from', _('Event start')),
    ('date_to', _('Event end')),
    ('date_admission', _('Event admission')),
    ('presale_start', _('Presale start')),
    ('presale_end', _('Presale end')),
)

RelativeDate = namedtuple('RelativeDate', ['days', 'minutes', 'time', 'is_after', 'base_date_name'], defaults=(0, None, None, False, 'date_from'))


class RelativeDateWrapper:
    """
    This contains information on a date that might be relative to an event. This means
    that the underlying data is either a fixed date or a number of days and a wall clock
    time to calculate the date based on a base point.

    The base point can be the date_from, date_to, date_admission, presale_start or presale_end
    attribute of an event or subevent. If the respective attribute is not set, ``date_from``
    will be used.
    """

    def __init__(self, data: Union[datetime.datetime, RelativeDate]):
        self.data = data

    def date(self, event) -> datetime.date:
        from .models import SubEvent

        if isinstance(self.data, datetime.datetime):
            return self.data.date()
        elif isinstance(self.data, datetime.date):
            return self.data
        else:
            if self.data.minutes is not None:
                raise ValueError('A minute-based relative datetime can not be used as a date')

            tz = ZoneInfo(event.settings.timezone)
            if isinstance(event, SubEvent):
                base_date = (
                    getattr(event, self.data.base_date_name)
                    or getattr(event.event, self.data.base_date_name)
                    or event.date_from
                )
            else:
                base_date = getattr(event, self.data.base_date_name) or event.date_from

            if self.data.is_after:
                new_date = base_date.astimezone(tz) + datetime.timedelta(days=self.data.days)
            else:
                new_date = base_date.astimezone(tz) - datetime.timedelta(days=self.data.days)
            return new_date.date()

    def datetime(self, event) -> datetime.datetime:
        from .models import SubEvent

        if isinstance(self.data, (datetime.datetime, datetime.date)):
            return self.data
        else:
            tz = ZoneInfo(event.settings.timezone)
            if isinstance(event, SubEvent):
                base_date = (
                    getattr(event, self.data.base_date_name)
                    or getattr(event.event, self.data.base_date_name)
                    or event.date_from
                )
            else:
                base_date = getattr(event, self.data.base_date_name) or event.date_from

            if self.data.minutes is not None:
                if self.data.is_after:
                    return base_date.astimezone(tz) + datetime.timedelta(minutes=self.data.minutes)
                else:
                    return base_date.astimezone(tz) - datetime.timedelta(minutes=self.data.minutes)
            else:
                if self.data.is_after:
                    new_date = (base_date.astimezone(tz) + datetime.timedelta(days=self.data.days)).astimezone(tz)
                else:
                    new_date = (base_date.astimezone(tz) - datetime.timedelta(days=self.data.days)).astimezone(tz)
                if self.data.time:
                    new_date = new_date.replace(
                        hour=self.data.time.hour,
                        minute=self.data.time.minute,
                        second=self.data.time.second
                    )
                new_date = new_date.astimezone(tz)
                return new_date

    def to_string(self) -> str:
        if isinstance(self.data, (datetime.datetime, datetime.date)):
            return self.data.isoformat()
        else:
            if self.data.minutes is not None:
                return 'RELDATE/minutes/{}/{}/{}'.format(  #
                    self.data.minutes,
                    self.data.base_date_name,
                    'after' if self.data.is_after else '',
                )
            return 'RELDATE/{}/{}/{}/{}'.format(  #
                self.data.days,
                self.data.time.strftime('%H:%M:%S') if self.data.time else '-',
                self.data.base_date_name,
                'after' if self.data.is_after else '',
            )

    @classmethod
    def from_string(cls, input: str):
        if input.startswith('RELDATE/'):
            parts = input.split('/')
            if parts[1] == 'minutes':
                data = RelativeDate(
                    days=0,
                    minutes=int(parts[2]),
                    base_date_name=parts[3],
                    time=None,
                    is_after=len(parts) > 4 and parts[4] == "after",
                )
            else:
                if parts[2] == '-':
                    time = None
                else:
                    timeparts = parts[2].split(':')
                    time = datetime.time(hour=int(timeparts[0]), minute=int(timeparts[1]), second=int(timeparts[2]))
                try:
                    data = RelativeDate(
                        days=int(parts[1] or 0),
                        base_date_name=parts[3],
                        time=time,
                        minutes=None,
                        is_after=len(parts) > 4 and parts[4] == "after",
                    )
                except ValueError:
                    data = RelativeDate(
                        days=0,
                        base_date_name=parts[3],
                        time=time,
                        minutes=None,
                        is_after=len(parts) > 4 and parts[4] == "after",
                    )
            if data.base_date_name not in [k[0] for k in BASE_CHOICES]:
                raise ValueError('{} is not a valid base date'.format(data.base_date_name))
        else:
            data = parser.parse(input)
        return RelativeDateWrapper(data)

    def __len__(self):
        return len(self.to_string())


BEFORE_AFTER_CHOICE = (
    ('before', _('before')),
    ('after', _('after')),
)


reldatetimeparts = namedtuple('reldatetimeparts', (
    "status",  # 0
    "absolute",  # 1
    "rel_days_number",  # 2
    "rel_mins_relationto",  # 3
    "rel_days_timeofday",  # 4
    "rel_mins_number",  # 5
    "rel_days_relationto",  # 6
    "rel_mins_relation",  # 7
    "rel_days_relation"  # 8
))
reldatetimeparts.indizes = reldatetimeparts(*range(9))


class RelativeDateTimeWidget(forms.MultiWidget):
    template_name = 'pretixbase/forms/widgets/reldatetime.html'
    parts = reldatetimeparts

    def __init__(self, *args, **kwargs):
        self.status_choices = kwargs.pop('status_choices')
        base_choices = kwargs.pop('base_choices')

        def placeholder_datetime_format():
            df = get_format('DATETIME_INPUT_FORMATS')[0]
            return now().replace(
                year=2000, month=12, day=31, hour=18, minute=0, second=0, microsecond=0
            ).strftime(df)

        def placeholder_time_format():
            tf = get_format('TIME_INPUT_FORMATS')[0]
            return datetime.time(8, 30, 0).strftime(tf)

        widgets = reldatetimeparts(
            status=forms.RadioSelect(choices=self.status_choices),
            absolute=forms.DateTimeInput(
                attrs={'placeholder': lazy(placeholder_datetime_format, str), 'class': 'datetimepicker'}
            ),
            rel_days_number=forms.NumberInput(),
            rel_mins_relationto=forms.Select(choices=base_choices),
            rel_days_timeofday=forms.TimeInput(
                attrs={'placeholder': lazy(placeholder_time_format, str), 'class': 'timepickerfield'}
            ),
            rel_mins_number=forms.NumberInput(),
            rel_days_relationto=forms.Select(choices=base_choices),
            rel_mins_relation=forms.Select(choices=BEFORE_AFTER_CHOICE),
            rel_days_relation=forms.Select(choices=BEFORE_AFTER_CHOICE),
        )
        super().__init__(widgets=widgets, *args, **kwargs)

    def decompress(self, value):
        if isinstance(value, str):
            value = RelativeDateWrapper.from_string(value)
        if isinstance(value, reldatetimeparts):
            return value
        if not value:
            return reldatetimeparts(
                status="unset",
                absolute=None,
                rel_days_number=1,
                rel_mins_relationto="date_from",
                rel_days_timeofday=None,
                rel_mins_number=0,
                rel_days_relationto="date_from",
                rel_mins_relation="before",
                rel_days_relation="before"
            )
        elif isinstance(value.data, (datetime.datetime, datetime.date)):
            return reldatetimeparts(
                status="absolute",
                absolute=value.data,
                rel_days_number=1,
                rel_mins_relationto="date_from",
                rel_days_timeofday=None,
                rel_mins_number=0,
                rel_days_relationto="date_from",
                rel_mins_relation="before",
                rel_days_relation="before"
            )
        elif value.data.minutes is not None:
            return reldatetimeparts(
                status="relative_minutes",
                absolute=None,
                rel_days_number=None,
                rel_mins_relationto=value.data.base_date_name,
                rel_days_timeofday=None,
                rel_mins_number=value.data.minutes,
                rel_days_relationto=value.data.base_date_name,
                rel_mins_relation="after" if value.data.is_after else "before",
                rel_days_relation="after" if value.data.is_after else "before"
            )
        return reldatetimeparts(
            status="relative",
            absolute=None,
            rel_days_number=value.data.days,
            rel_mins_relationto=value.data.base_date_name,
            rel_days_timeofday=value.data.time,
            rel_mins_number=0,
            rel_days_relationto=value.data.base_date_name,
            rel_mins_relation="after" if value.data.is_after else "before",
            rel_days_relation="after" if value.data.is_after else "before"
        )

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx['required'] = self.status_choices[0][0] == 'unset'

        ctx['rendered_subwidgets'] = self.parts(*(
            self._render(w['template_name'], {**ctx, 'widget': w})
            for w in ctx['widget']['subwidgets']
        ))._asdict()

        return ctx


class RelativeDateTimeField(forms.MultiValueField):
    def __init__(self, *args, **kwargs):
        status_choices = [
            ('absolute', _('Fixed date:')),
            ('relative', _('Relative date:')),
            ('relative_minutes', _('Relative time:')),
        ]
        if kwargs.get('limit_choices'):
            limit = kwargs.pop('limit_choices')
            choices = [(k, v) for k, v in BASE_CHOICES if k in limit]
        else:
            choices = BASE_CHOICES
        if not kwargs.get('required', True):
            status_choices.insert(0, ('unset', _('Not set')))
        fields = reldatetimeparts(
            status=forms.ChoiceField(
                choices=status_choices,
                required=True
            ),
            absolute=forms.DateTimeField(
                required=False
            ),
            rel_days_number=forms.IntegerField(
                required=False
            ),
            rel_mins_relationto=forms.ChoiceField(
                choices=choices,
                required=False
            ),
            rel_days_timeofday=forms.TimeField(
                required=False,
            ),
            rel_mins_number=forms.IntegerField(
                required=False
            ),
            rel_days_relationto=forms.ChoiceField(
                choices=choices,
                required=False
            ),
            rel_mins_relation=forms.ChoiceField(
                choices=BEFORE_AFTER_CHOICE,
                required=False
            ),
            rel_days_relation=forms.ChoiceField(
                choices=BEFORE_AFTER_CHOICE,
                required=False
            ),
        )
        if 'widget' not in kwargs:
            kwargs['widget'] = RelativeDateTimeWidget(status_choices=status_choices, base_choices=choices)
        kwargs.pop('max_length', 0)
        kwargs.pop('empty_value', 0)
        super().__init__(
            fields=fields, require_all_fields=False, *args, **kwargs
        )

    def set_event(self, event):
        self.widget.widgets[reldatetimeparts.indizes.rel_days_relationto].choices = [
            (k, v) for k, v in BASE_CHOICES if getattr(event, k, None)
        ]
        self.widget.widgets[reldatetimeparts.indizes.rel_mins_relationto].choices = [
            (k, v) for k, v in BASE_CHOICES if getattr(event, k, None)
        ]

    def compress(self, data_list):
        if not data_list:
            return None
        data = reldatetimeparts(*data_list)
        if data.status == 'absolute':
            return RelativeDateWrapper(data.absolute)
        elif data.status == 'unset':
            return None
        elif data.status == 'relative_minutes':
            return RelativeDateWrapper(RelativeDate(
                days=0,
                base_date_name=data.rel_mins_relationto,
                time=None,
                minutes=data.rel_mins_number,
                is_after=data.rel_mins_relation == "after",
            ))
        else:
            return RelativeDateWrapper(RelativeDate(
                days=data.rel_days_number,
                base_date_name=data.rel_days_relationto,
                time=data.rel_days_timeofday,
                minutes=None,
                is_after=data.rel_days_relation == "after",
            ))

    def has_changed(self, initial, data):
        if initial is None:
            initial = self.widget.decompress(initial)
        return super().has_changed(initial, data)

    def clean(self, value):
        data = reldatetimeparts(*value)
        if data.status == 'absolute' and not data.absolute:
            raise ValidationError(self.error_messages['incomplete'])
        elif data.status == 'relative' and (data.rel_days_number is None or not data.rel_days_relationto):
            raise ValidationError(self.error_messages['incomplete'])
        elif data.status == 'relative_minutes' and (data.rel_mins_number is None or not data.rel_mins_relationto):
            raise ValidationError(self.error_messages['incomplete'])

        return super().clean(value)


reldateparts = namedtuple('reldateparts', (
    "status",  # 0
    "absolute",  # 1
    "rel_days_number",  # 2
    "rel_days_relationto",  # 3
    "rel_days_relation",  # 4
))
reldateparts.indizes = reldateparts(*range(5))


class RelativeDateWidget(RelativeDateTimeWidget):
    template_name = 'pretixbase/forms/widgets/reldate.html'
    parts = reldateparts

    def __init__(self, *args, **kwargs):
        self.status_choices = kwargs.pop('status_choices')
        widgets = reldateparts(
            status=forms.RadioSelect(choices=self.status_choices),
            absolute=forms.DateInput(
                attrs={'class': 'datepickerfield'}
            ),
            rel_days_number=forms.NumberInput(),
            rel_days_relationto=forms.Select(choices=kwargs.pop('base_choices')),
            rel_days_relation=forms.Select(choices=BEFORE_AFTER_CHOICE),
        )
        forms.MultiWidget.__init__(self, widgets=widgets, *args, **kwargs)

    def decompress(self, value):
        if isinstance(value, str):
            value = RelativeDateWrapper.from_string(value)
        if not value:
            return reldateparts(
                status="unset",
                absolute=None,
                rel_days_number=1,
                rel_days_relationto="date_from",
                rel_days_relation="before"
            )
        if isinstance(value, reldateparts):
            return value
        elif isinstance(value.data, (datetime.datetime, datetime.date)):
            return reldateparts(
                status="absolute",
                absolute=value.data,
                rel_days_number=1,
                rel_days_relationto="date_from",
                rel_days_relation="before"
            )
        return reldateparts(
            status="relative",
            absolute=None,
            rel_days_number=value.data.days,
            rel_days_relationto=value.data.base_date_name,
            rel_days_relation="after" if value.data.is_after else "before"
        )


class RelativeDateField(RelativeDateTimeField):

    def __init__(self, *args, **kwargs):
        status_choices = [
            ('absolute', _('Fixed date:')),
            ('relative', _('Relative date:')),
        ]
        if not kwargs.get('required', True):
            status_choices.insert(0, ('unset', _('Not set')))
        fields = reldateparts(
            status=forms.ChoiceField(
                choices=status_choices,
                required=True
            ),
            absolute=forms.DateField(
                required=False
            ),
            rel_days_number=forms.IntegerField(
                required=False
            ),
            rel_days_relationto=forms.ChoiceField(
                choices=BASE_CHOICES,
                required=False
            ),
            rel_days_relation=forms.ChoiceField(
                choices=BEFORE_AFTER_CHOICE,
                required=False
            ),
        )
        if 'widget' not in kwargs:
            kwargs['widget'] = RelativeDateWidget(status_choices=status_choices, base_choices=BASE_CHOICES)
        forms.MultiValueField.__init__(
            self, fields=fields, require_all_fields=False, *args, **kwargs
        )

    def set_event(self, event):
        self.widget.widgets[reldateparts.indizes.rel_days_relationto].choices = [
            (k, v) for k, v in BASE_CHOICES if getattr(event, k, None)
        ]

    def compress(self, data_list):
        if not data_list:
            return None
        data = reldateparts(*data_list)
        if data.status == 'absolute':
            return RelativeDateWrapper(data.absolute)
        elif data.status == 'unset':
            return None
        else:
            return RelativeDateWrapper(RelativeDate(
                days=data.rel_days_number,
                base_date_name=data.rel_days_relationto,
                time=None, minutes=None,
                is_after=data.rel_days_relation == "after"
            ))

    def clean(self, value):
        data = reldateparts(*value)
        if data.status == 'absolute' and not data.absolute:
            raise ValidationError(self.error_messages['incomplete'])
        elif data.status == 'relative' and (data.rel_days_number is None or not data.rel_days_relationto):
            raise ValidationError(self.error_messages['incomplete'])

        return forms.MultiValueField.clean(self, value)


class ModelRelativeDateTimeField(models.CharField):
    form_class = RelativeDateTimeField

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        kwargs.setdefault('max_length', 255)
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if isinstance(value, RelativeDateWrapper):
            return value
        if value is None:
            return None
        return RelativeDateWrapper.from_string(value)

    def get_prep_value(self, value):
        if isinstance(value, RelativeDateWrapper):
            return value.to_string()
        return value

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        return RelativeDateWrapper.from_string(value)

    def formfield(self, **kwargs):
        defaults = {'form_class': self.form_class}
        defaults.update(kwargs)
        return super().formfield(**defaults)


class SerializerRelativeDateField(serializers.CharField):

    def to_internal_value(self, data):
        if data is None:
            return None
        try:
            r = RelativeDateWrapper.from_string(data)
            if isinstance(r.data, RelativeDate):
                if r.data.time is not None:
                    raise ValidationError("Do not specify a time for a date field")
            return r
        except:
            raise ValidationError("Invalid relative date")

    def to_representation(self, value: RelativeDateWrapper):
        if value is None:
            return None
        return value.to_string()


class SerializerRelativeDateTimeField(serializers.CharField):

    def to_internal_value(self, data):
        if data is None:
            return None
        try:
            return RelativeDateWrapper.from_string(data)
        except:
            raise ValidationError("Invalid relative date")

    def to_representation(self, value: RelativeDateWrapper):
        if value is None:
            return None
        return value.to_string()
