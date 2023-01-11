from datetime import datetime, date

import pytest
import pytz

from pretix.control.timeframes import REPORTING_DATE_TIMEFRAMES

tz = pytz.timezone("Europe/Berlin")


def dt(*args):
    return tz.localize(datetime(*args))


ref_date = date(2023, 3, 28)


@pytest.mark.parametrize("ref_dt,identifier,expected_start,expected_end", [
    (ref_date, 'days_today', date(2023, 3, 28), date(2023, 3, 28)),
    (ref_date, 'days_last7', date(2023, 3, 22), date(2023, 3, 28)),
    (ref_date, 'days_last14', date(2023, 3, 15), date(2023, 3, 28)),
    (ref_date, 'days_tomorrow', date(2023, 3, 29), date(2023, 3, 29)),
    (ref_date, 'days_next7', date(2023, 3, 29), date(2023, 4, 4)),
    (ref_date, 'days_next14', date(2023, 3, 29), date(2023, 4, 11)),
    (ref_date, 'week_this', date(2023, 3, 27), date(2023, 4, 2)),
    (ref_date, 'week_to_date', date(2023, 3, 27), date(2023, 3, 28)),
    (ref_date, 'week_previous', date(2023, 3, 20), date(2023, 3, 26)),
    (ref_date, 'week_next', date(2023, 4, 3), date(2023, 4, 9)),
    (ref_date, 'month_this', date(2023, 3, 1), date(2023, 3, 31)),
    (ref_date, 'month_to_date', date(2023, 3, 1), date(2023, 3, 28)),
    (ref_date, 'month_previous', date(2023, 2, 1), date(2023, 2, 28)),
    (ref_date, 'month_next', date(2023, 4, 1), date(2023, 4, 30)),
    (ref_date, 'quarter_this', date(2023, 1, 1), date(2023, 3, 31)),
    (ref_date, 'quarter_to_date', date(2023, 1, 1), date(2023, 3, 28)),
    (ref_date, 'quarter_previous', date(2022, 10, 1), date(2022, 12, 31)),
    (ref_date, 'quarter_next', date(2023, 4, 1), date(2023, 6, 30)),
    (ref_date, 'year_this', date(2023, 1, 1), date(2023, 12, 31)),
    (ref_date, 'year_to_date', date(2023, 1, 1), date(2023, 3, 28)),
    (ref_date, 'year_previous', date(2022, 1, 1), date(2022, 12, 31)),
    (ref_date, 'year_next', date(2024, 1, 1), date(2024, 12, 31)),
])
def test_timeframe(ref_dt, identifier, expected_start, expected_end):
    for idf, label, start, end, includes_future in REPORTING_DATE_TIMEFRAMES:
        if identifier == idf:
            assert start(ref_dt) == expected_start
            assert end(ref_dt, expected_start) == expected_end
            assert includes_future == (expected_end > ref_dt)
            break
    else:
        assert False, "identifier not found"
