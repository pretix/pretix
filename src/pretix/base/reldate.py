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
import os
import warnings
from collections import namedtuple
from typing import (
    TYPE_CHECKING, Iterable, List, Literal, Tuple, Union,
)
from zoneinfo import ZoneInfo

from dateutil import parser
from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.formats import get_format
from django.utils.functional import Promise, lazy
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

if TYPE_CHECKING:
    from .models import Event, Order, SubEvent


class BaseChoice:
    def __init__(self, base: Literal["event", "order"], attribute: str, text: Promise, supports_before: bool,
                 supports_after: bool) -> None:
        self.base = base
        self.attribute = attribute
        self.text = text
        self.supports_before = supports_before
        self.supports_after = supports_after
        self.key = f"{self.base}__{self.attribute}"

    @staticmethod
    def find(objects: Iterable["BaseChoice"], key: str) -> "BaseChoice":
        if "__" in key:
            choice = next((obj for obj in objects if obj.key == key), None)
        else:
            # fallback for RelativeDateFields stored, before support for bases other than event was added
            choice = next((obj for obj in objects if obj.attribute == key and obj.base == "event"), None)

        if choice is None:
            raise TypeError(f"key {key} must be a valid key in BASE_CHOICES")

        return choice


BASE_CHOICES: List[BaseChoice] = [
    BaseChoice('event', 'date_from', _('Event start'), True, True),
    BaseChoice('event', 'date_to', _('Event end'), True, True),
    BaseChoice('event', 'date_admission', _('Event admission'), True, True),
    BaseChoice('event', 'presale_start', _('Presale start'), True, True),
    BaseChoice('event', 'presale_end', _('Presale end'), True, True),
    BaseChoice('order', 'datetime', _('Order creation'), False, True),
    BaseChoice('order', 'expires', _('Order expiry'), True, True),
]

LIMIT_FALLBACKS = ['date_from', 'date_to', 'date_admission', 'presale_start', 'presale_end']

EVENT_BASE_CHOICES = [
    x for x in BASE_CHOICES if x.base == 'event'
]

ORDER_BASE_CHOICES = [
    x for x in BASE_CHOICES if x.base == 'order'
]


class RelativeDate:
    """
    This contains information on a date that is defined in relation to a fixed base point.
    This means that the underlying data is a fixed date as the base point and a number of days or a time interval
    to calculate the date.

    The list of valid base date choices is defined in BASE_CHOICES.
    If the base_date_key is not set, the date_from attribute of Event is used.
    """

    def __init__(self, days: int = 0, minutes: int = None, time: datetime.time = None, is_after: bool = False,
                 base_date_name: str = 'event__date_from') -> None:
        choice = BaseChoice.find(BASE_CHOICES, base_date_name)
        self.base = choice.base
        self.attribute = choice.attribute

        if is_after and not choice.supports_after:
            raise ValueError(
                "The selected base date and attribute combination does not support relative dates placed after the base date"
            )
        if not is_after and not choice.supports_before:
            raise ValueError(
                "The selected base date and attribute combination does not support relative dates placed before the base date")
        self.is_after = is_after

        self.days = days
        self.minutes = minutes
        self.time = time
        self.key = choice.key

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, RelativeDate):
            return False
        return self.to_string() == o.to_string()

    def _resolve_base_date(self, base: "Event | Order | SubEvent") -> Tuple[datetime.datetime, ZoneInfo]:
        """

        :param base:
        :return:
        """
        from .models import Event, Order, SubEvent

        if self.base == "order" and isinstance(base, Order):
            event = base.event
            base_date = getattr(base, self.attribute)
        elif self.base == "event" and isinstance(base, SubEvent):
            event = base.event
            base_date = (getattr(base, self.attribute) or
                         getattr(base.event, self.attribute) or
                         base.date_from)
        elif self.base == "event" and isinstance(base, Event):
            event = base
            base_date = getattr(base, self.attribute) or event.date_from
        else:
            raise TypeError("The base defined by data does not match the passed in base")

        tz = ZoneInfo(event.settings.timezone)
        return base_date, tz

    def date(self, base: "Event | Order | SubEvent") -> datetime.date:
        if self.minutes is not None:
            raise ValueError('A minute-based relative datetime can not be used as a date')

        base_date, tz = self._resolve_base_date(base)

        if self.is_after:
            new_date = base_date.astimezone(tz) + datetime.timedelta(days=self.days)
        else:
            new_date = base_date.astimezone(tz) - datetime.timedelta(days=self.days)
        return new_date.date()

    def datetime(self, base: "Event | Order | SubEvent") -> datetime.datetime:
        base_date, tz = self._resolve_base_date(base)

        if self.minutes is not None:
            if self.is_after:
                return base_date.astimezone(tz) + datetime.timedelta(minutes=self.minutes)
            else:
                return base_date.astimezone(tz) - datetime.timedelta(minutes=self.minutes)
        else:
            if self.is_after:
                new_date = (base_date.astimezone(tz) + datetime.timedelta(days=self.days)).astimezone(tz)
            else:
                new_date = (base_date.astimezone(tz) - datetime.timedelta(days=self.days)).astimezone(tz)
            if self.time:
                new_date = new_date.replace(
                    hour=self.time.hour,
                    minute=self.time.minute,
                    second=self.time.second
                )
            new_date = new_date.astimezone(tz)
            return new_date

    def to_string(self) -> str:
        """

        :return:
        """
        if self.minutes is not None:
            return 'RELDATE/minutes/{}/{}/{}'.format(  #
                self.minutes,
                self.key,
                'after' if self.is_after else '',
            )
        return 'RELDATE/{}/{}/{}/{}'.format(  #
            self.days,
            self.time.strftime('%H:%M:%S') if self.time else '-',
            self.key,
            'after' if self.is_after else '',
        )

    @classmethod
    def from_string(cls, input: str):
        """

        :param input:
        """
        if not input.startswith('RELDATE/'):
            raise TypeError("Invalid input for RelativeDate.from_string()")

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

        return data


class RelativeDateWrapper:
    """
    This contains information on a date that might be relative to an event. This means
    that the underlying data is either a fixed date or a number of days and a wall clock
    time to calculate the date based on a base point.
    """

    def __init__(self, data: Union[datetime.datetime, RelativeDate]):
        self.data = data

    def date(self, base: "Event | Order | SubEvent") -> datetime.date:
        if isinstance(self.data, datetime.datetime):
            return self.data.date()
        elif isinstance(self.data, datetime.date):
            return self.data
        else:
            return self.data.date(base)

    def datetime(self, base: "Event | Order | SubEvent") -> datetime.datetime:
        if isinstance(self.data, (datetime.datetime, datetime.date)):
            return self.data
        else:
            return self.data.datetime(base)

    def to_string(self) -> str:
        if isinstance(self.data, (datetime.datetime, datetime.date)):
            return self.data.isoformat()
        else:
            return self.data.to_string()

    @classmethod
    def from_string(cls, input: str):
        if input.startswith('RELDATE/'):
            data = RelativeDate.from_string(input)
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
                rel_mins_relationto="event__date_from",
                rel_days_timeofday=None,
                rel_mins_number=0,
                rel_days_relationto="event__date_from",
                rel_mins_relation="before",
                rel_days_relation="before"
            )
        elif isinstance(value.data, (datetime.datetime, datetime.date)):
            return reldatetimeparts(
                status="absolute",
                absolute=value.data,
                rel_days_number=1,
                rel_mins_relationto="event__date_from",
                rel_days_timeofday=None,
                rel_mins_number=0,
                rel_days_relationto="event__date_from",
                rel_mins_relation="before",
                rel_days_relation="before"
            )
        elif value.data.minutes is not None:
            return reldatetimeparts(
                status="relative_minutes",
                absolute=None,
                rel_days_number=None,
                rel_mins_relationto=value.data.key,
                rel_days_timeofday=None,
                rel_mins_number=value.data.minutes,
                rel_days_relationto=value.data.key,
                rel_mins_relation="after" if value.data.is_after else "before",
                rel_days_relation="after" if value.data.is_after else "before"
            )
        return reldatetimeparts(
            status="relative",
            absolute=None,
            rel_days_number=value.data.days,
            rel_mins_relationto=value.data.key,
            rel_days_timeofday=value.data.time,
            rel_mins_number=0,
            rel_days_relationto=value.data.key,
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
        self.relative_to_order = kwargs.pop('relative_to_order', False)

        all_choices = EVENT_BASE_CHOICES
        if self.relative_to_order:
            all_choices.extend(ORDER_BASE_CHOICES)

        if kwargs.get('limit_choices'):
            limit = kwargs.pop('limit_choices')
            if any("__" not in l for l in limit):
                _warn_skips = (os.path.dirname(__file__),)
                warnings.warn(
                    "Please prefix limit_choices with the base the attributes refer to, for example event__date_from",
                    skip_file_prefixes=_warn_skips)

            choices = [(c.key, c.text) for c in all_choices if
                       # new base case as we want limit_choices to be expressed as base__attribute
                       (c.key in limit) or
                       # fallback for old event based entries
                       # if the base is an event, then using only attribute is fine
                       (c.base == "event" and c.attribute in limit)]
        else:
            choices = [(c.key, c.text) for c in all_choices]

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
        choices = [
            (c.key, c.text) for c in EVENT_BASE_CHOICES if getattr(event, c.attribute, None)
        ]
        if self.relative_to_order:
            choices += [(c.key, c.text) for c in ORDER_BASE_CHOICES]
        self.widget.widgets[reldatetimeparts.indizes.rel_days_relationto].choices = choices
        self.widget.widgets[reldatetimeparts.indizes.rel_mins_relationto].choices = choices

    def compress(self, data_list):
        if not data_list:
            return None
        data = reldatetimeparts(*data_list)
        if data.status == 'unset':
            return None
        elif data.status == 'absolute':
            return RelativeDateWrapper(data.absolute)
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
        elif data.status == 'relative':
            choice = BaseChoice.find(BASE_CHOICES, data.rel_days_relationto)
            if data.rel_days_relation == "before" and not choice.supports_before:
                raise ValidationError(_("A relative date cannot be expressed as 'before' for '{}'".format(choice.text)))
            elif data.status == 'relative' and data.rel_days_relation == "after" and not choice.supports_after:
                raise ValidationError(_("A relative date cannot be expressed as 'after' for '{}'".format(choice.text)))
        elif data.status == 'relative_minutes':
            choice = BaseChoice.find(BASE_CHOICES, data.rel_days_relationto)
            if data.rel_days_relation == "before" and not choice.supports_before:
                raise ValidationError(_("A relative time cannot be expressed as 'before' for '{}'".format(choice.text)))
            elif data.rel_days_relation == "after" and not choice.supports_after:
                raise ValidationError(_("A relative time cannot be expressed as 'after' for '{}'".format(choice.text)))

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
        base_choices = kwargs.pop('base_choices')
        widgets = reldateparts(
            status=forms.RadioSelect(choices=self.status_choices),
            absolute=forms.DateInput(
                attrs={'class': 'datepickerfield'}
            ),
            rel_days_number=forms.NumberInput(),
            rel_days_relationto=forms.Select(choices=base_choices),
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

        choices = [(c.key, c.text) for c in EVENT_BASE_CHOICES]
        self.relative_to_order = kwargs.pop('relative_to_order', False)
        if self.relative_to_order:
            choices += [(c.key, c.text) for c in ORDER_BASE_CHOICES]

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
                choices=choices,
                required=False
            ),
            rel_days_relation=forms.ChoiceField(
                choices=BEFORE_AFTER_CHOICE,
                required=False
            ),
        )
        if 'widget' not in kwargs:
            kwargs['widget'] = RelativeDateWidget(status_choices=status_choices, base_choices=choices)
        forms.MultiValueField.__init__(
            self, fields=fields, require_all_fields=False, *args, **kwargs
        )

    def set_event(self, event):
        choices = [
            (c.key, c.text) for c in EVENT_BASE_CHOICES if getattr(event, c.attribute, None)
        ]
        if self.relative_to_order:
            choices += [(c.key, c.text) for c in ORDER_BASE_CHOICES]
        self.widget.widgets[reldateparts.indizes.rel_days_relationto].choices = choices

    def compress(self, data_list):
        if not data_list:
            return None
        data = reldateparts(*data_list)
        if data.status == 'unset':
            return None
        elif data.status == 'absolute':
            return RelativeDateWrapper(data.absolute)
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
        if data.status == 'relative':
            choice = BaseChoice.find(BASE_CHOICES, data.rel_days_relationto)
            if data.rel_days_number is None or not data.rel_days_relationto:
                raise ValidationError(self.error_messages['incomplete'])
            elif data.rel_days_relation == "before" and not choice.supports_before:
                raise ValidationError(_("A relative date cannot be expressed as 'before' for '{}'".format(choice.text)))
            elif data.rel_days_relation == "after" and not choice.supports_after:
                raise ValidationError(_("A relative date cannot be expressed as 'after' for '{}'".format(choice.text)))

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
