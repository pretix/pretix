import datetime
from collections import namedtuple
from typing import Union

import pytz
from dateutil import parser
from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import ugettext_lazy as _

BASE_CHOICES = (
    ('date_from', _('Event start')),
    ('date_to', _('Event end')),
    ('date_admission', _('Event admission')),
    ('presale_start', _('Presale start')),
    ('presale_end', _('Presale end')),
)

RelativeDate = namedtuple('RelativeDate', ['days_before', 'time', 'base_date_name'])


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

    def date(self, event) -> datetime.datetime:
        from .models import SubEvent

        if isinstance(self.data, datetime.date):
            return self.data
        elif isinstance(self.data, datetime.datetime):
            return self.data.date()
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

            oldoffset = base_date.utcoffset()
            new_date = base_date.astimezone(tz) - datetime.timedelta(days=self.data.days_before)
            if self.data.time:
                new_date = new_date.replace(
                    hour=self.data.time.hour,
                    minute=self.data.time.minute,
                    second=self.data.time.second
                )
            new_date = new_date.astimezone(tz)
            newoffset = new_date.utcoffset()
            new_date += oldoffset - newoffset
            return new_date

    def to_string(self) -> str:
        if isinstance(self.data, (datetime.datetime, datetime.date)):
            return self.data.isoformat()
        else:
            return 'RELDATE/{}/{}/{}/'.format(  #
                self.data.days_before,
                self.data.time.strftime('%H:%M:%S') if self.data.time else '-',
                self.data.base_date_name
            )

    @classmethod
    def from_string(cls, input: str):
        if input.startswith('RELDATE/'):
            parts = input.split('/')
            if parts[2] == '-':
                time = None
            else:
                timeparts = parts[2].split(':')
                time = datetime.time(hour=int(timeparts[0]), minute=int(timeparts[1]), second=int(timeparts[2]))
            data = RelativeDate(
                days_before=int(parts[1] or 0),
                base_date_name=parts[3],
                time=time
            )
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
            forms.TimeInput(attrs={'placeholder': _('Time'), 'class': 'timepickerfield'})
        )
        super().__init__(widgets=widgets, *args, **kwargs)

    def decompress(self, value):
        if isinstance(value, str):
            value = RelativeDateWrapper.from_string(value)
        if not value:
            return ['unset', None, 1, 'date_from', None]
        elif isinstance(value.data, (datetime.datetime, datetime.date)):
            return ['absolute', value.data, 1, 'date_from', None]
        return ['relative', None, value.data.days_before, value.data.base_date_name, value.data.time]

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx['required'] = self.status_choices[0][0] == 'unset'
        return ctx


class RelativeDateTimeField(forms.MultiValueField):
    def __init__(self, *args, **kwargs):
        status_choices = [
            ('absolute', _('Fixed date:')),
            ('relative', _('Relative date:')),
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
        else:
            return RelativeDateWrapper(RelativeDate(
                days_before=data_list[2],
                base_date_name=data_list[3],
                time=data_list[4]
            ))

    def clean(self, value):
        if value[0] == 'absolute' and not value[1]:
            raise ValidationError(self.error_messages['incomplete'])
        elif value[0] == 'relative' and (value[2] is None or not value[3]):
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
                time=None
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

    def from_db_value(self, value, expression, connection, context):
        if value is None:
            return None
        return RelativeDateWrapper.from_string(value)

    def formfield(self, **kwargs):
        defaults = {'form_class': self.form_class}
        defaults.update(kwargs)
        return super().formfield(**defaults)
