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
from datetime import date, datetime, time, timedelta
from typing import Tuple

from django import forms
from django.core.exceptions import ValidationError
from django.utils.formats import date_format
from django.utils.timezone import make_aware, now
from django.utils.translation import gettext_lazy, pgettext_lazy


def _quarter_start(ref_d):
    return ref_d.replace(day=1, month=1 + (ref_d.month - 1) // 3 * 3)


def _week_start(ref_d):
    return ref_d - timedelta(ref_d.weekday())


REPORTING_DATE_TIMEFRAMES = (
    # (identifier, label, start_inclusive, end_inclusive, includes_future)
    (
        'days_today',
        pgettext_lazy('reporting_timeframe', 'Today'),
        lambda ref_d: ref_d,
        lambda ref_d, start_d: start_d,
        False,
    ),
    (
        'days_last7',
        pgettext_lazy('reporting_timeframe', 'Last 7 days'),
        lambda ref_d: ref_d - timedelta(days=6),
        lambda ref_d, start_d: start_d + timedelta(days=6),
        False,
    ),
    (
        'days_last14',
        pgettext_lazy('reporting_timeframe', 'Last 14 days'),
        lambda ref_d: ref_d - timedelta(days=13),
        lambda ref_d, start_d: start_d + timedelta(days=13),
        False,
    ),
    (
        'days_tomorrow',
        pgettext_lazy('reporting_timeframe', 'Tomorrow'),
        lambda ref_d: ref_d + timedelta(days=1),
        lambda ref_d, start_d: start_d,
        True,
    ),
    (
        'days_next7',
        pgettext_lazy('reporting_timeframe', 'Next 7 days'),
        lambda ref_d: ref_d + timedelta(days=1),
        lambda ref_d, start_d: start_d + timedelta(days=6),
        True,
    ),
    (
        'days_next14',
        pgettext_lazy('reporting_timeframe', 'Next 14 days'),
        lambda ref_d: ref_d + timedelta(days=1),
        lambda ref_d, start_d: start_d + timedelta(days=13),
        True,
    ),
    (
        'week_this',
        pgettext_lazy('reporting_timeframe', 'Current week'),
        lambda ref_d: _week_start(ref_d),
        lambda ref_d, start_d: start_d + timedelta(days=6),
        True,
    ),
    (
        'week_to_date',
        pgettext_lazy('reporting_timeframe', 'Current week to date'),
        lambda ref_d: _week_start(ref_d),
        lambda ref_d, start_d: ref_d,
        False,
    ),
    (
        'week_previous',
        pgettext_lazy('reporting_timeframe', 'Previous week'),
        lambda ref_d: _week_start(ref_d) - timedelta(days=7),
        lambda ref_d, start_d: start_d + timedelta(days=6),
        False,
    ),
    (
        'week_next',
        pgettext_lazy('reporting_timeframe', 'Next week'),
        lambda ref_d: _week_start(ref_d + timedelta(days=7)),
        lambda ref_d, start_d: start_d + timedelta(days=6),
        True,
    ),
    (
        'month_this',
        pgettext_lazy('reporting_timeframe', 'Current month'),
        lambda ref_d: ref_d.replace(day=1),
        lambda ref_d, start_d: start_d.replace(day=calendar.monthrange(start_d.year, start_d.month)[1]),
        True,
    ),
    (
        'month_to_date',
        pgettext_lazy('reporting_timeframe', 'Current month to date'),
        lambda ref_d: ref_d.replace(day=1),
        lambda ref_d, start_d: ref_d,
        False,
    ),
    (
        'month_previous',
        pgettext_lazy('reporting_timeframe', 'Previous month'),
        lambda ref_d: (ref_d.replace(day=1) - timedelta(days=1)).replace(day=1),
        lambda ref_d, start_d: start_d.replace(day=calendar.monthrange(start_d.year, start_d.month)[1]),
        False,
    ),
    (
        'month_next',
        pgettext_lazy('reporting_timeframe', 'Next month'),
        lambda ref_d: ref_d.replace(day=calendar.monthrange(ref_d.year, ref_d.month)[1]) + timedelta(days=1),
        lambda ref_d, start_d: start_d.replace(day=calendar.monthrange(start_d.year, start_d.month)[1]),
        True,
    ),
    (
        'quarter_this',
        pgettext_lazy('reporting_timeframe', 'Current quarter'),
        lambda ref_d: _quarter_start(ref_d),
        lambda ref_d, start_d: start_d.replace(day=calendar.monthrange(start_d.year, start_d.month + 2)[1], month=start_d.month + 2),
        True,
    ),
    (
        'quarter_to_date',
        pgettext_lazy('reporting_timeframe', 'Current quarter to date'),
        lambda ref_d: _quarter_start(ref_d),
        lambda ref_d, start_d: ref_d,
        False,
    ),
    (
        'quarter_previous',
        pgettext_lazy('reporting_timeframe', 'Previous quarter'),
        lambda ref_d: _quarter_start(_quarter_start(ref_d) - timedelta(days=1)),
        lambda ref_d, start_d: start_d.replace(day=calendar.monthrange(start_d.year, start_d.month + 2)[1], month=start_d.month + 2),
        False,
    ),
    (
        'quarter_next',
        pgettext_lazy('reporting_timeframe', 'Next quarter'),
        lambda ref_d: ref_d.replace(
            day=calendar.monthrange(ref_d.year, _quarter_start(ref_d).month + 2)[1], month=_quarter_start(ref_d).month + 2
        ) + timedelta(days=1),
        lambda ref_d, start_d: start_d.replace(day=calendar.monthrange(start_d.year, start_d.month + 2)[1], month=start_d.month + 2),
        True,
    ),
    (
        'year_this',
        pgettext_lazy('reporting_timeframe', 'Current year'),
        lambda ref_d: ref_d.replace(day=1, month=1),
        lambda ref_d, start_d: start_d.replace(day=31, month=12),
        True,
    ),
    (
        'year_to_date',
        pgettext_lazy('reporting_timeframe', 'Current year to date'),
        lambda ref_d: ref_d.replace(day=1, month=1),
        lambda ref_d, start_d: ref_d,
        False,
    ),
    (
        'year_previous',
        pgettext_lazy('reporting_timeframe', 'Previous year'),
        lambda ref_d: (ref_d.replace(day=1, month=1) - timedelta(days=1)).replace(day=1, month=1),
        lambda ref_d, start_d: start_d.replace(day=31, month=12),
        False,
    ),
    (
        'year_next',
        pgettext_lazy('reporting_timeframe', 'Next year'),
        lambda ref_d: ref_d.replace(day=1, month=1, year=ref_d.year + 1),
        lambda ref_d, start_d: start_d.replace(day=31, month=12),
        True,
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
                date.fromisoformat(value.split('/', 1)[0]),
                date.fromisoformat(value.split('/', 1)[-1]),
            ]
        return []

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx['required'] = self.timeframe_choices[0][0] == 'unset'
        return ctx


class DateFrameField(forms.MultiValueField):
    def __init__(self, *args, **kwargs):
        include_future_frames = kwargs.pop('include_future_frames')
        timeframe_choices = [
            (identifier, f'{label} ({date_format(start(now()), "SHORT_DATE_FORMAT")} - {date_format(end(now(), start(now())), "SHORT_DATE_FORMAT")})')
            for identifier, label, start, end, future in REPORTING_DATE_TIMEFRAMES
            if include_future_frames or not future
        ]
        timeframe_choices.insert(0, ('custom', gettext_lazy('Custom timeframe')))
        if not kwargs.get('required', True):
            timeframe_choices.insert(0, ('unset', pgettext_lazy('reporting_timeframe', 'All time')))
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
            return f'{data_list[1].isoformat()}/{data_list[2].isoformat()}'
        else:
            return data_list[0]

    def has_changed(self, initial, data):
        if initial is None:
            initial = self.widget.decompress(initial)
        return super().has_changed(initial, data)

    def clean(self, value):
        if value[0] == 'custom':
            if not value[1] or not value[2]:
                raise ValidationError(self.error_messages['incomplete'])
            # todo validate start<end
        return super().clean(value)


def resolve_timeframe_to_dates_inclusive(ref_dt, frame, timezone) -> Tuple[date, date]:
    """
    Given a serialized timeframe, evaluate it relative to `ref_dt` and return a tuple of dates
    where the first element ist the first possible date value within the timeframe and the second
    element is the last possible date value in the tiemframe.
    """
    if isinstance(ref_dt, datetime):
        ref_dt = ref_dt.astimezone(timezone).date()
    if "/" in frame:
        start, end = frame.split("/", 1)
        return date.fromisoformat(start), date.fromisoformat(end)
    for idf, label, start, end, includes_future in REPORTING_DATE_TIMEFRAMES:
        if frame == idf:
            d_start = start(ref_dt)
            d_end = end(ref_dt, d_start)
            return d_start, d_end
    raise ValueError(f"Invalid timeframe '{frame}'")


def resolve_timeframe_to_datetime_start_inclusive_end_exclusive(ref_dt, frame, timezone) -> Tuple[datetime, datetime]:
    """
    Given a serialized timeframe, evaluate it relative to `ref_dt` and return a tuple of datetimes
    where the first element ist the first possible datetime within the timeframe and the second
    element is the first possible datetime value *not* in the tiemframe.
    """
    if isinstance(ref_dt, datetime):
        ref_dt = ref_dt.astimezone(timezone).date()
    if "/" in frame:
        start, end = frame.split("/", 1)
        d_start = date.fromisoformat(start)
        d_end = date.fromisoformat(end)
    else:
        for idf, label, start, end, includes_future in REPORTING_DATE_TIMEFRAMES:
            if frame == idf:
                d_start = start(ref_dt)
                d_end = end(ref_dt, d_start)
                break
        else:
            raise ValueError(f"Invalid timeframe '{frame}'")

    dt_start = make_aware(datetime.combine(d_start, time(0, 0, 0)), timezone)
    dt_end = make_aware(datetime.combine(d_end + timedelta(days=1), time(0, 0, 0)), timezone)
    return dt_start, dt_end
