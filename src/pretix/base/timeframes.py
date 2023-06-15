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
import calendar
from datetime import date, datetime, time, timedelta, timezone
from itertools import groupby
from typing import Optional, Tuple

from django import forms
from django.core.exceptions import ValidationError
from django.utils.formats import date_format
from django.utils.timezone import make_aware, now
from django.utils.translation import gettext_lazy, pgettext_lazy
from rest_framework import serializers

from pretix.helpers.daterange import daterange


def _quarter_start(ref_d):
    return ref_d.replace(day=1, month=1 + (ref_d.month - 1) // 3 * 3)


def _week_start(ref_d):
    return ref_d - timedelta(ref_d.weekday())


REPORTING_DATE_TIMEFRAMES = (
    # (identifier, label, start_inclusive, end_inclusive, includes_future, optgroup, describe)
    (
        'days_today',
        pgettext_lazy('reporting_timeframe', 'Today'),
        lambda ref_d: ref_d,
        lambda ref_d, start_d: start_d,
        False,
        pgettext_lazy('reporting_timeframe', 'by day'),
        daterange
    ),
    (
        'days_yesterday',
        pgettext_lazy('reporting_timeframe', 'Yesterday'),
        lambda ref_d: ref_d - timedelta(days=1),
        lambda ref_d, start_d: start_d,
        False,
        pgettext_lazy('reporting_timeframe', 'by day'),
        daterange
    ),
    (
        'days_last7',
        pgettext_lazy('reporting_timeframe', 'Last 7 days'),
        lambda ref_d: ref_d - timedelta(days=6),
        lambda ref_d, start_d: start_d + timedelta(days=6),
        False,
        pgettext_lazy('reporting_timeframe', 'by day'),
        daterange
    ),
    (
        'days_last14',
        pgettext_lazy('reporting_timeframe', 'Last 14 days'),
        lambda ref_d: ref_d - timedelta(days=13),
        lambda ref_d, start_d: start_d + timedelta(days=13),
        False,
        pgettext_lazy('reporting_timeframe', 'by day'),
        daterange
    ),
    (
        'days_tomorrow',
        pgettext_lazy('reporting_timeframe', 'Tomorrow'),
        lambda ref_d: ref_d + timedelta(days=1),
        lambda ref_d, start_d: start_d,
        True,
        pgettext_lazy('reporting_timeframe', 'by day'),
        daterange
    ),
    (
        'days_next7',
        pgettext_lazy('reporting_timeframe', 'Next 7 days'),
        lambda ref_d: ref_d + timedelta(days=1),
        lambda ref_d, start_d: start_d + timedelta(days=6),
        True,
        pgettext_lazy('reporting_timeframe', 'by day'),
        daterange
    ),
    (
        'days_next14',
        pgettext_lazy('reporting_timeframe', 'Next 14 days'),
        lambda ref_d: ref_d + timedelta(days=1),
        lambda ref_d, start_d: start_d + timedelta(days=13),
        True,
        pgettext_lazy('reporting_timeframe', 'by day'),
        daterange
    ),
    (
        'week_this',
        pgettext_lazy('reporting_timeframe', 'Current week'),
        lambda ref_d: _week_start(ref_d),
        lambda ref_d, start_d: start_d + timedelta(days=6),
        True,
        pgettext_lazy('reporting_timeframe', 'by week'),
        lambda start_d, end_d: date_format(start_d, 'WEEK_FORMAT') + ' - ' + daterange(start_d, end_d),
    ),
    (
        'week_to_date',
        pgettext_lazy('reporting_timeframe', 'Current week to date'),
        lambda ref_d: _week_start(ref_d),
        lambda ref_d, start_d: ref_d,
        False,
        pgettext_lazy('reporting_timeframe', 'by week'),
        lambda start_d, end_d: date_format(start_d, 'WEEK_FORMAT') + ' - ' + daterange(start_d, end_d),
    ),
    (
        'week_previous',
        pgettext_lazy('reporting_timeframe', 'Previous week'),
        lambda ref_d: _week_start(ref_d) - timedelta(days=7),
        lambda ref_d, start_d: start_d + timedelta(days=6),
        False,
        pgettext_lazy('reporting_timeframe', 'by week'),
        lambda start_d, end_d: date_format(start_d, 'WEEK_FORMAT') + ' - ' + daterange(start_d, end_d),
    ),
    (
        'week_next',
        pgettext_lazy('reporting_timeframe', 'Next week'),
        lambda ref_d: _week_start(ref_d + timedelta(days=7)),
        lambda ref_d, start_d: start_d + timedelta(days=6),
        True,
        pgettext_lazy('reporting_timeframe', 'by week'),
        lambda start_d, end_d: date_format(start_d, 'WEEK_FORMAT') + ' - ' + daterange(start_d, end_d),
    ),
    (
        'month_this',
        pgettext_lazy('reporting_timeframe', 'Current month'),
        lambda ref_d: ref_d.replace(day=1),
        lambda ref_d, start_d: start_d.replace(day=calendar.monthrange(start_d.year, start_d.month)[1]),
        True,
        pgettext_lazy('reporting_timeframe', 'by month'),
        lambda start_d, end_d: date_format(start_d, 'YEAR_MONTH_FORMAT'),
    ),
    (
        'month_to_date',
        pgettext_lazy('reporting_timeframe', 'Current month to date'),
        lambda ref_d: ref_d.replace(day=1),
        lambda ref_d, start_d: ref_d,
        False,
        pgettext_lazy('reporting_timeframe', 'by month'),
        lambda start_d, end_d: date_format(start_d, 'YEAR_MONTH_FORMAT'),
    ),
    (
        'month_previous',
        pgettext_lazy('reporting_timeframe', 'Previous month'),
        lambda ref_d: (ref_d.replace(day=1) - timedelta(days=1)).replace(day=1),
        lambda ref_d, start_d: start_d.replace(day=calendar.monthrange(start_d.year, start_d.month)[1]),
        False,
        pgettext_lazy('reporting_timeframe', 'by month'),
        lambda start_d, end_d: date_format(start_d, 'YEAR_MONTH_FORMAT'),
    ),
    (
        'month_next',
        pgettext_lazy('reporting_timeframe', 'Next month'),
        lambda ref_d: ref_d.replace(day=calendar.monthrange(ref_d.year, ref_d.month)[1]) + timedelta(days=1),
        lambda ref_d, start_d: start_d.replace(day=calendar.monthrange(start_d.year, start_d.month)[1]),
        True,
        pgettext_lazy('reporting_timeframe', 'by month'),
        lambda start_d, end_d: date_format(start_d, 'YEAR_MONTH_FORMAT'),
    ),
    (
        'quarter_this',
        pgettext_lazy('reporting_timeframe', 'Current quarter'),
        lambda ref_d: _quarter_start(ref_d),
        lambda ref_d, start_d: start_d.replace(day=calendar.monthrange(start_d.year, start_d.month + 2)[1], month=start_d.month + 2),
        True,
        pgettext_lazy('reporting_timeframe', 'by quarter'),
        lambda start_d, end_d: f"Q{(start_d.month - 1) // 3 + 1}/{start_d.year}",
    ),
    (
        'quarter_to_date',
        pgettext_lazy('reporting_timeframe', 'Current quarter to date'),
        lambda ref_d: _quarter_start(ref_d),
        lambda ref_d, start_d: ref_d,
        False,
        pgettext_lazy('reporting_timeframe', 'by quarter'),
        lambda start_d, end_d: f"Q{(start_d.month - 1) // 3 + 1}/{start_d.year}",
    ),
    (
        'quarter_previous',
        pgettext_lazy('reporting_timeframe', 'Previous quarter'),
        lambda ref_d: _quarter_start(_quarter_start(ref_d) - timedelta(days=1)),
        lambda ref_d, start_d: start_d.replace(day=calendar.monthrange(start_d.year, start_d.month + 2)[1], month=start_d.month + 2),
        False,
        pgettext_lazy('reporting_timeframe', 'by quarter'),
        lambda start_d, end_d: f"Q{(start_d.month - 1) // 3 + 1}/{start_d.year}",
    ),
    (
        'quarter_next',
        pgettext_lazy('reporting_timeframe', 'Next quarter'),
        lambda ref_d: ref_d.replace(
            day=calendar.monthrange(ref_d.year, _quarter_start(ref_d).month + 2)[1], month=_quarter_start(ref_d).month + 2
        ) + timedelta(days=1),
        lambda ref_d, start_d: start_d.replace(day=calendar.monthrange(start_d.year, start_d.month + 2)[1], month=start_d.month + 2),
        True,
        pgettext_lazy('reporting_timeframe', 'by quarter'),
        lambda start_d, end_d: f"Q{(start_d.month - 1) // 3 + 1}/{start_d.year}",
    ),
    (
        'year_this',
        pgettext_lazy('reporting_timeframe', 'Current year'),
        lambda ref_d: ref_d.replace(day=1, month=1),
        lambda ref_d, start_d: start_d.replace(day=31, month=12),
        True,
        pgettext_lazy('reporting_timeframe', 'by year'),
        lambda start_d, end_d: str(start_d.year),
    ),
    (
        'year_to_date',
        pgettext_lazy('reporting_timeframe', 'Current year to date'),
        lambda ref_d: ref_d.replace(day=1, month=1),
        lambda ref_d, start_d: ref_d,
        False,
        pgettext_lazy('reporting_timeframe', 'by year'),
        lambda start_d, end_d: str(start_d.year),
    ),
    (
        'year_previous',
        pgettext_lazy('reporting_timeframe', 'Previous year'),
        lambda ref_d: (ref_d.replace(day=1, month=1) - timedelta(days=1)).replace(day=1, month=1),
        lambda ref_d, start_d: start_d.replace(day=31, month=12),
        False,
        pgettext_lazy('reporting_timeframe', 'by year'),
        lambda start_d, end_d: str(start_d.year),
    ),
    (
        'year_next',
        pgettext_lazy('reporting_timeframe', 'Next year'),
        lambda ref_d: ref_d.replace(day=1, month=1, year=ref_d.year + 1),
        lambda ref_d, start_d: start_d.replace(day=31, month=12),
        True,
        pgettext_lazy('reporting_timeframe', 'by year'),
        lambda start_d, end_d: str(start_d.year),
    ),
    (
        'future',
        pgettext_lazy('reporting_timeframe', 'All future (excluding today)'),
        lambda ref_d: ref_d + timedelta(days=1),
        lambda ref_d, start_d: None,
        True,
        pgettext_lazy('reporting_timeframe', 'Other'),
        lambda start_d, end_d: date_format(start_d, "SHORT_DATE_FORMAT") + ' – ',
    ),
    (
        'past',
        pgettext_lazy('reporting_timeframe', 'All past (including today)'),
        lambda ref_d: None,
        lambda ref_d, start_d: ref_d,
        True,  # technically false, but only makes sense to have in a selection that also allows the future, otherwise redundant
        pgettext_lazy('reporting_timeframe', 'Other'),
        lambda start_d, end_d: ' – ' + date_format(end_d, "SHORT_DATE_FORMAT"),
    ),
)


class DateFrameWidget(forms.MultiWidget):
    template_name = 'pretixbase/forms/widgets/dateframe.html'

    def __init__(self, *args, **kwargs):
        self.timeframe_choices = kwargs.pop('timeframe_choices')
        widgets = (
            forms.Select(choices=self.timeframe_choices),
            forms.DateInput(attrs={'class': 'datepickerfield', 'placeholder': pgettext_lazy('timeframe', 'Start')}),
            forms.DateInput(attrs={'class': 'datepickerfield', 'placeholder': pgettext_lazy('timeframe', 'End')}),
        )
        super().__init__(widgets=widgets, *args, **kwargs)

    def decompress(self, value):
        if not value:
            return ['unset', None, None]
        if '/' in value:
            return [
                'custom',
                date.fromisoformat(value.split('/', 1)[0]) if value.split('/', 1)[0] else None,
                date.fromisoformat(value.split('/', 1)[-1]) if value.split('/', 1)[-1] else None,
            ]
        return [value, None, None]

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx['required'] = self.timeframe_choices[0][0] == 'unset'
        ctx['widget']['subwidgets'][1]['attrs'].pop('required', None)
        ctx['widget']['subwidgets'][2]['attrs'].pop('required', None)
        return ctx


def _describe_timeframe(label, start, end, future, describe):
    d_start = start(now())
    d_end = end(now(), d_start)
    details = describe(d_start, d_end)
    return f'{label} ({details})'


class DateFrameField(forms.MultiValueField):
    default_error_messages = {
        **forms.MultiValueField.default_error_messages,
        'inconsistent': gettext_lazy('The end date must be after the start date.'),
    }

    def __init__(self, *args, **kwargs):
        include_future_frames = kwargs.pop('include_future_frames')

        top_choices = [('custom', gettext_lazy('Custom timeframe'))]
        if not kwargs.get('required', True):
            top_choices.insert(0, ('unset', pgettext_lazy('reporting_timeframe', 'All time')))

        _choices = []
        for grouper, group in groupby(REPORTING_DATE_TIMEFRAMES, key=lambda i: i[5]):
            options = [
                (identifier, _describe_timeframe(label, start, end, future, describe))
                for identifier, label, start, end, future, group, describe in group
                if include_future_frames or not future
            ]
            if options:
                _choices.append((grouper, options))

        timeframe_choices = [
            ('', top_choices)
        ] + _choices

        fields = (
            forms.ChoiceField(
                choices=timeframe_choices,
                required=True
            ),
            forms.DateField(
                required=False
            ),
            forms.DateField(
                required=False
            ),
        )
        if 'widget' not in kwargs:
            kwargs['widget'] = DateFrameWidget(timeframe_choices=timeframe_choices)
        kwargs.pop('max_length', 0)
        kwargs.pop('empty_value', 0)
        super().__init__(
            fields=fields, require_all_fields=False, *args, **kwargs
        )

    def compress(self, data_list):
        if not data_list:
            return None
        if data_list[0] == 'unset':
            return None
        elif data_list[0] == 'custom':
            return f'{data_list[1].isoformat() if data_list[1] else ""}/{data_list[2].isoformat() if data_list[2] else ""}'
        else:
            return data_list[0]

    def has_changed(self, initial, data):
        if initial is None:
            initial = self.widget.decompress(initial)
        return super().has_changed(initial, data)

    def clean(self, value):
        if not value:
            return None
        if value[0] == 'custom':
            if not value[1] and not value[2]:
                raise ValidationError(self.error_messages['incomplete'])
            if value[1] and value[2] and self.fields[2].to_python(value[2]) < self.fields[1].to_python(value[1]):
                raise ValidationError(self.error_messages['inconsistent'])
        return super().clean(value)


class SerializerDateFrameField(serializers.CharField):

    def to_internal_value(self, data):
        if data is None:
            return None
        try:
            resolve_timeframe_to_dates_inclusive(now(), data, timezone.utc)
        except:
            raise ValidationError("Invalid date frame")

    def to_representation(self, value):
        if value is None:
            return None
        return value


def resolve_timeframe_to_dates_inclusive(ref_dt, frame, timezone) -> Tuple[Optional[date], Optional[date]]:
    """
    Given a serialized timeframe, evaluate it relative to `ref_dt` and return a tuple of dates
    where the first element ist the first possible date value within the timeframe and the second
    element is the last possible date value in the timeframe.
    Both returned values may be ``None`` for an unlimited interval.
    """
    if isinstance(ref_dt, datetime):
        ref_dt = ref_dt.astimezone(timezone).date()
    if "/" in frame:
        start, end = frame.split("/", 1)
        return date.fromisoformat(start) if start else None, date.fromisoformat(end) if end else None
    for idf, label, start, end, includes_future, *args in REPORTING_DATE_TIMEFRAMES:
        if frame == idf:
            d_start = start(ref_dt)
            d_end = end(ref_dt, d_start)
            return d_start, d_end
    raise ValueError(f"Invalid timeframe '{frame}'")


def resolve_timeframe_to_datetime_start_inclusive_end_exclusive(ref_dt, frame, timezone) -> Tuple[Optional[date], Optional[date]]:
    """
    Given a serialized timeframe, evaluate it relative to `ref_dt` and return a tuple of datetimes
    where the first element ist the first possible datetime within the timeframe and the second
    element is the first possible datetime value *not* in the timeframe.
    Both returned values may be ``None`` for an unlimited interval.
    """
    d_start, d_end = resolve_timeframe_to_dates_inclusive(ref_dt, frame, timezone)
    dt_start = make_aware(datetime.combine(d_start, time(0, 0, 0)), timezone) if d_start else None
    dt_end = make_aware(datetime.combine(d_end + timedelta(days=1), time(0, 0, 0)), timezone) if d_end else None
    return dt_start, dt_end
