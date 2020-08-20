import datetime
from collections import namedtuple
from typing import Union

import pytz
from dateutil import parser
from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

BASE_CHOICES = (
    ('date_from', _('Event start')),
    ('date_to', _('Event end')),
    ('date_admission', _('Event admission')),
    ('presale_start', _('Presale start')),
    ('presale_end', _('Presale end')),
)

RelativeDate = namedtuple('RelativeDate', ['days_before', 'minutes_before', 'time', 'base_date_name'])


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

        if isinstance(self.data, datetime.date):
            return self.data
        elif isinstance(self.data, datetime.datetime):
            return self.data.date()
        else:
            if self.data.minutes_before is not None:
                raise ValueError('A minute-based relative datetime can not be used as a date')

            tz = pytz.timezone(event.settings.timezone)
            if isinstance(event, SubEvent):
                base_date = (
                    getattr(event, self.data.base_date_name)
                    or getattr(event.event, self.data.base_date_name)
                    or event.date_from
                )
            else:
                base_date = getattr(event, self.data.base_date_name) or event.date_from

            new_date = base_date.astimezone(tz) - datetime.timedelta(days=self.data.days_before)
            return new_date.date()

    def datetime(self, event) -> datetime.datetime:
        from .models import SubEvent

        if isinstance(self.data, (datetime.datetime, datetime.date)):
            return self.data
        else:
            tz = pytz.timezone(event.settings.timezone)
            if isinstance(event, SubEvent):
                base_date = (
                    getattr(event, self.data.base_date_name)
                    or getattr(event.event, self.data.base_date_name)
                    or event.date_from
                )
            else:
                base_date = getattr(event, self.data.base_date_name) or event.date_from

            if self.data.minutes_before is not None:
                return base_date.astimezone(tz) - datetime.timedelta(minutes=self.data.minutes_before)
            else:
                oldoffset = base_date.astimezone(tz).utcoffset()
                new_date = base_date.astimezone(tz) - datetime.timedelta(days=self.data.days_before)
                if self.data.time:
                    new_date = new_date.replace(
                        hour=self.data.time.hour,
                        minute=self.data.time.minute,
                        second=self.data.time.second
                    )
                new_date = new_date.astimezone(tz)
                new_offset = new_date.utcoffset()
                new_date += oldoffset - new_offset
                return new_date

    def to_string(self) -> str:
        if isinstance(self.data, (datetime.datetime, datetime.date)):
            return self.data.isoformat()
        else:
            if self.data.minutes_before is not None:
                return 'RELDATE/minutes/{}/{}/'.format(  #
                    self.data.minutes_before,
                    self.data.base_date_name
                )
            return 'RELDATE/{}/{}/{}/'.format(  #
                self.data.days_before,
                self.data.time.strftime('%H:%M:%S') if self.data.time else '-',
                self.data.base_date_name
            )

    @classmethod
    def from_string(cls, input: str):
        if input.startswith('RELDATE/'):
            parts = input.split('/')
            if parts[1] == 'minutes':
                data = RelativeDate(
                    days_before=0,
                    minutes_before=int(parts[2]),
                    base_date_name=parts[3],
                    time=None
                )
            else:
                if parts[2] == '-':
                    time = None
                else:
                    timeparts = parts[2].split(':')
                    time = datetime.time(hour=int(timeparts[0]), minute=int(timeparts[1]), second=int(timeparts[2]))
                try:
                    data = RelativeDate(
                        days_before=int(parts[1] or 0),
                        base_date_name=parts[3],
                        time=time,
                        minutes_before=None
                    )
                except ValueError:
                    data = RelativeDate(
                        days_before=0,
                        base_date_name=parts[3],
                        time=time,
                        minutes_before=None
                    )
            if data.base_date_name not in [k[0] for k in BASE_CHOICES]:
                raise ValueError('{} is not a valid base date'.format(data.base_date_name))
        else:
            data = parser.parse(input)
        return RelativeDateWrapper(data)

    def __len__(self):
        return len(self.to_string())


class RelativeDateTimeWidget(forms.MultiWidget):
    template_name = 'pretixbase/forms/widgets/reldatetime.html'

    def __init__(self, *args, **kwargs):
        self.status_choices = kwargs.pop('status_choices')
        widgets = (
            forms.RadioSelect(choices=self.status_choices),
            forms.DateTimeInput(
                attrs={'class': 'datetimepicker'}
            ),
            forms.NumberInput(),
            forms.Select(choices=kwargs.pop('base_choices')),
            forms.TimeInput(attrs={'placeholder': _('Time'), 'class': 'timepickerfield'}),
            forms.NumberInput(),
        )
        super().__init__(widgets=widgets, *args, **kwargs)

    def decompress(self, value):
        if isinstance(value, str):
            value = RelativeDateWrapper.from_string(value)
        if not value:
            return ['unset', None, 1, 'date_from', None, 0]
        elif isinstance(value.data, (datetime.datetime, datetime.date)):
            return ['absolute', value.data, 1, 'date_from', None, 0]
        elif value.data.minutes_before is not None:
            return ['relative_minutes', None, None, value.data.base_date_name, None, value.data.minutes_before]
        return ['relative', None, value.data.days_before, value.data.base_date_name, value.data.time, 0]

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx['required'] = self.status_choices[0][0] == 'unset'
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
        fields = (
            forms.ChoiceField(
                choices=status_choices,
                required=True
            ),
            forms.DateTimeField(
                required=False
            ),
            forms.IntegerField(
                required=False
            ),
            forms.ChoiceField(
                choices=choices,
                required=False
            ),
            forms.TimeField(
                required=False,
            ),
            forms.IntegerField(
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
        self.widget.widgets[3].choices = [
            (k, v) for k, v in BASE_CHOICES if getattr(event, k, None)
        ]

    def compress(self, data_list):
        if not data_list:
            return None
        if data_list[0] == 'absolute':
            return RelativeDateWrapper(data_list[1])
        elif data_list[0] == 'unset':
            return None
        elif data_list[0] == 'relative_minutes':
            return RelativeDateWrapper(RelativeDate(
                days_before=0,
                base_date_name=data_list[3],
                time=None,
                minutes_before=data_list[5]
            ))
        else:
            return RelativeDateWrapper(RelativeDate(
                days_before=data_list[2],
                base_date_name=data_list[3],
                time=data_list[4],
                minutes_before=None
            ))

    def clean(self, value):
        if value[0] == 'absolute' and not value[1]:
            raise ValidationError(self.error_messages['incomplete'])
        elif value[0] == 'relative' and (value[2] is None or not value[3]):
            raise ValidationError(self.error_messages['incomplete'])
        elif value[0] == 'relative_minutes' and (value[5] is None or not value[3]):
            raise ValidationError(self.error_messages['incomplete'])

        return super().clean(value)


class RelativeDateWidget(RelativeDateTimeWidget):
    template_name = 'pretixbase/forms/widgets/reldate.html'

    def __init__(self, *args, **kwargs):
        self.status_choices = kwargs.pop('status_choices')
        widgets = (
            forms.RadioSelect(choices=self.status_choices),
            forms.DateInput(
                attrs={'class': 'datepickerfield'}
            ),
            forms.NumberInput(),
            forms.Select(choices=kwargs.pop('base_choices')),
        )
        forms.MultiWidget.__init__(self, widgets=widgets, *args, **kwargs)

    def decompress(self, value):
        if isinstance(value, str):
            value = RelativeDateWrapper.from_string(value)
        if not value:
            return ['unset', None, 1, 'date_from']
        elif isinstance(value.data, (datetime.datetime, datetime.date)):
            return ['absolute', value.data, 1, 'date_from']
        return ['relative', None, value.data.days_before, value.data.base_date_name]


class RelativeDateField(RelativeDateTimeField):

    def __init__(self, *args, **kwargs):
        status_choices = [
            ('absolute', _('Fixed date:')),
            ('relative', _('Relative date:')),
        ]
        if not kwargs.get('required', True):
            status_choices.insert(0, ('unset', _('Not set')))
        fields = (
            forms.ChoiceField(
                choices=status_choices,
                required=True
            ),
            forms.DateField(
                required=False
            ),
            forms.IntegerField(
                required=False
            ),
            forms.ChoiceField(
                choices=BASE_CHOICES,
                required=False
            ),
        )
        if 'widget' not in kwargs:
            kwargs['widget'] = RelativeDateWidget(status_choices=status_choices, base_choices=BASE_CHOICES)
        forms.MultiValueField.__init__(
            self, fields=fields, require_all_fields=False, *args, **kwargs
        )

    def compress(self, data_list):
        if not data_list:
            return None
        if data_list[0] == 'absolute':
            return RelativeDateWrapper(data_list[1])
        elif data_list[0] == 'unset':
            return None
        else:
            return RelativeDateWrapper(RelativeDate(
                days_before=data_list[2],
                base_date_name=data_list[3],
                time=None, minutes_before=None
            ))

    def clean(self, value):
        if value[0] == 'absolute' and not value[1]:
            raise ValidationError(self.error_messages['incomplete'])
        elif value[0] == 'relative' and (value[2] is None or not value[3]):
            raise ValidationError(self.error_messages['incomplete'])

        return super().clean(value)


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
