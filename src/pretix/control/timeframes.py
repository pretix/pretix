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
from datetime import timedelta

from django.utils.translation import pgettext_lazy


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
