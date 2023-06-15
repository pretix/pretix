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

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from pretix.base.timeframes import (
    REPORTING_DATE_TIMEFRAMES, resolve_timeframe_to_dates_inclusive,
    resolve_timeframe_to_datetime_start_inclusive_end_exclusive,
)

tz = ZoneInfo("Europe/Berlin")


def dt(*args):
    return datetime(*args, tzinfo=tz)


ref_date = date(2023, 3, 28)


@pytest.mark.parametrize("ref_dt,identifier,expected_start,expected_end,description", [
    (ref_date, 'days_today', date(2023, 3, 28), date(2023, 3, 28), None),
    (ref_date, 'days_yesterday', date(2023, 3, 27), date(2023, 3, 27), None),
    (ref_date, 'days_last7', date(2023, 3, 22), date(2023, 3, 28), None),
    (ref_date, 'days_last14', date(2023, 3, 15), date(2023, 3, 28), None),
    (ref_date, 'days_tomorrow', date(2023, 3, 29), date(2023, 3, 29), None),
    (ref_date, 'days_next7', date(2023, 3, 29), date(2023, 4, 4), None),
    (ref_date, 'days_next14', date(2023, 3, 29), date(2023, 4, 11), None),
    (ref_date, 'week_this', date(2023, 3, 27), date(2023, 4, 2), 'W 13, 2023 - March 27th – April 2nd, 2023'),
    (ref_date, 'week_to_date', date(2023, 3, 27), date(2023, 3, 28), 'W 13, 2023 - March 27th – 28th, 2023'),
    (ref_date, 'week_previous', date(2023, 3, 20), date(2023, 3, 26), 'W 12, 2023 - March 20th – 26th, 2023'),
    (ref_date, 'week_next', date(2023, 4, 3), date(2023, 4, 9), 'W 14, 2023 - April 3rd – 9th, 2023'),
    (ref_date, 'month_this', date(2023, 3, 1), date(2023, 3, 31), 'March 2023'),
    (ref_date, 'month_to_date', date(2023, 3, 1), date(2023, 3, 28), 'March 2023'),
    (ref_date, 'month_previous', date(2023, 2, 1), date(2023, 2, 28), 'February 2023'),
    (ref_date, 'month_next', date(2023, 4, 1), date(2023, 4, 30), 'April 2023'),
    (ref_date, 'quarter_this', date(2023, 1, 1), date(2023, 3, 31), 'Q1/2023'),
    (ref_date, 'quarter_to_date', date(2023, 1, 1), date(2023, 3, 28), 'Q1/2023'),
    (ref_date, 'quarter_previous', date(2022, 10, 1), date(2022, 12, 31), 'Q4/2022'),
    (ref_date, 'quarter_next', date(2023, 4, 1), date(2023, 6, 30), 'Q2/2023'),
    (ref_date, 'year_this', date(2023, 1, 1), date(2023, 12, 31), '2023'),
    (ref_date, 'year_to_date', date(2023, 1, 1), date(2023, 3, 28), '2023'),
    (ref_date, 'year_previous', date(2022, 1, 1), date(2022, 12, 31), '2022'),
    (ref_date, 'year_next', date(2024, 1, 1), date(2024, 12, 31), '2024'),
    (ref_date, 'future', date(2023, 3, 29), None, '2023-03-29 – '),
    (ref_date, 'past', None, date(2023, 3, 28), ' – 2023-03-28'),
])
def test_timeframe(ref_dt, identifier, expected_start, expected_end, description):
    for idf, label, start, end, includes_future, group, describe in REPORTING_DATE_TIMEFRAMES:
        if identifier == idf:
            assert start(ref_dt) == expected_start
            assert end(ref_dt, expected_start) == expected_end
            if expected_end and expected_start:
                assert includes_future == (expected_end > ref_dt)
            if description:
                assert describe(expected_start, expected_end) == description
            break
    else:
        assert False, "identifier not found"


def test_resolve():
    assert resolve_timeframe_to_dates_inclusive(ref_date, "week_previous", tz) == (
        date(2023, 3, 20),
        date(2023, 3, 26),
    )
    assert resolve_timeframe_to_datetime_start_inclusive_end_exclusive(ref_date, "week_previous", tz) == (
        dt(2023, 3, 20, 0, 0, 0, 0),
        dt(2023, 3, 27, 0, 0, 0, 0),
    )

    assert resolve_timeframe_to_dates_inclusive(ref_date, "2023-03-20/2023-03-21", tz) == (
        date(2023, 3, 20),
        date(2023, 3, 21),
    )
    assert resolve_timeframe_to_datetime_start_inclusive_end_exclusive(ref_date, "2023-03-20/2023-03-21", tz) == (
        dt(2023, 3, 20, 0, 0, 0, 0),
        dt(2023, 3, 22, 0, 0, 0, 0),
    )

    assert resolve_timeframe_to_dates_inclusive(ref_date, "2023-03-20/", tz) == (
        date(2023, 3, 20),
        None
    )
    assert resolve_timeframe_to_datetime_start_inclusive_end_exclusive(ref_date, "2023-03-20/", tz) == (
        dt(2023, 3, 20, 0, 0, 0, 0),
        None
    )
