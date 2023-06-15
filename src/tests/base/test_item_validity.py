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
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pretix.base.models import Item

tz = ZoneInfo("Europe/Berlin")


def dt(*args, **kwargs):
    return datetime(*args, **kwargs, tzinfo=tz)


@pytest.mark.parametrize("minutes,hours,days,months,start,expected_end", [
    # Simple cases
    (0, 0, 0, 0, dt(2023, 2, 9, 10, 30, 0), dt(2023, 2, 9, 10, 30, 0)),  # zero case
    (10, 0, 0, 0, dt(2023, 2, 9, 10, 30, 0), dt(2023, 2, 9, 10, 40, 0)),  # "10 minute pass"
    (0, 1, 0, 0, dt(2023, 2, 9, 10, 30, 0), dt(2023, 2, 9, 11, 30, 0)),  # "hour pass"
    (10, 1, 0, 0, dt(2023, 2, 9, 10, 30, 0), dt(2023, 2, 9, 11, 40, 0)),  # "1h 10min pass"
    (0, 0, 1, 0, dt(2023, 2, 9, 10, 30, 0), dt(2023, 2, 9, 23, 59, 59)),  # "day pass"
    (0, 0, 3, 0, dt(2023, 2, 9, 10, 30, 0), dt(2023, 2, 11, 23, 59, 59)),  # "3-day pass"
    (30, 6, 3, 0, dt(2023, 2, 9, 10, 30, 0), dt(2023, 2, 12, 6, 29, 59)),  # "3-day pass with day end at 6:30"
    (0, 0, 0, 1, dt(2023, 2, 9, 10, 30, 0), dt(2023, 3, 8, 23, 59, 59)),  # "month pass"
    (0, 0, 3, 1, dt(2023, 2, 9, 10, 30, 0), dt(2023, 3, 11, 23, 59, 59)),  # "month pass + 3 days"
    (30, 6, 0, 1, dt(2023, 2, 9, 10, 30, 0), dt(2023, 3, 9, 6, 29, 59)),  # "month pass with day end at 6:30"
    (30, 6, 1, 1, dt(2023, 2, 9, 10, 30, 0), dt(2023, 3, 10, 6, 29, 59)),  # "month pass + 1 day with day end at 6:30"
    (0, 0, 0, 12, dt(2023, 2, 9, 10, 30, 0), dt(2024, 2, 8, 23, 59, 59)),  # "year pass"
    (0, 0, 0, 12, dt(2023, 1, 1, 10, 30, 0), dt(2023, 12, 31, 23, 59, 59)),  # "year pass"
    (30, 6, 0, 12, dt(2023, 2, 9, 10, 30, 0), dt(2024, 2, 9, 6, 29, 59)),  # "year pass with day end at 6:30"

    # Calendrical edge cases

    # Multi-day across a DST change
    (0, 0, 2, 0, dt(2023, 3, 25, 10, 30, 0), dt(2023, 3, 26, 23, 59, 59)),

    # Month + day across a DST change
    (0, 0, 1, 1, dt(2023, 2, 26, 10, 30, 0), dt(2023, 3, 26, 23, 59, 59)),

    # Day + hour with possibly non-existent end time during DST change
    (30, 2, 1, 0, dt(2023, 3, 25, 10, 30, 0), dt(2023, 3, 26, 3, 29, 59)),

    # Day + hour with ambiguous end time during DST change
    (30, 2, 1, 0, dt(2023, 10, 28, 10, 30, 0), dt(2023, 10, 29, 2, 29, 59, fold=1)),

    # Month with short month following
    (0, 0, 0, 1, dt(2023, 1, 31, 10, 30, 0), dt(2023, 2, 28, 23, 59, 59)),
    (0, 0, 0, 1, dt(2023, 1, 30, 10, 30, 0), dt(2023, 2, 28, 23, 59, 59)),
    (0, 0, 0, 1, dt(2023, 1, 29, 10, 30, 0), dt(2023, 2, 28, 23, 59, 59)),
    (0, 0, 0, 1, dt(2023, 1, 28, 10, 30, 0), dt(2023, 2, 27, 23, 59, 59)),
    (0, 0, 0, 1, dt(2023, 2, 1, 10, 30, 0), dt(2023, 2, 28, 23, 59, 59)),

    # Interaction on months and leap days
    (0, 0, 0, 1, dt(2024, 1, 31, 10, 30, 0), dt(2024, 2, 29, 23, 59, 59)),
    (0, 0, 0, 12, dt(2023, 3, 1, 10, 30, 0), dt(2024, 2, 29, 23, 59, 59)),
    (0, 0, 0, 12, dt(2024, 3, 1, 10, 30, 0), dt(2025, 2, 28, 23, 59, 59)),
    (0, 0, 0, 12, dt(2024, 2, 29, 10, 30, 0), dt(2025, 2, 28, 23, 59, 59)),
    (0, 0, 0, 12, dt(2024, 1, 31, 10, 30, 0), dt(2025, 1, 30, 23, 59, 59)),
])
def test_dynamic_validity(minutes, hours, days, months, start, expected_end):
    i = Item(
        validity_mode="dynamic",
        validity_dynamic_start_choice=True,
        validity_dynamic_duration_minutes=minutes,
        validity_dynamic_duration_hours=hours,
        validity_dynamic_duration_days=days,
        validity_dynamic_duration_months=months,
    )
    assert i.compute_validity(requested_start=start, override_tz=tz) == (start, expected_end)


def test_fixed_validity():
    i = Item(
        validity_mode="fixed",
        validity_fixed_from=dt(2023, 2, 9, 10, 15, 0),
        validity_fixed_until=dt(2023, 2, 9, 12, 15, 0),
    )
    assert i.compute_validity(requested_start=dt(2024, 1, 1, 0, 0, 0), override_tz=tz) == (
        i.validity_fixed_from, i.validity_fixed_until
    )


def test_fixed_validity_one_sided():
    i = Item(
        validity_mode="fixed",
        validity_fixed_from=dt(2023, 2, 9, 10, 15, 0),
        validity_fixed_until=None,
    )
    assert i.compute_validity(requested_start=dt(2024, 1, 1, 0, 0, 0), override_tz=tz) == (i.validity_fixed_from, None)
    i = Item(
        validity_mode="fixed",
        validity_fixed_from=None,
        validity_fixed_until=dt(2023, 2, 9, 10, 15, 0),
    )
    assert i.compute_validity(requested_start=dt(2024, 1, 1, 0, 0, 0), override_tz=tz) == (None, i.validity_fixed_until)


def test_default_validity():
    i = Item(
        validity_mode=None,
        validity_fixed_from=dt(2023, 2, 9, 10, 15, 0),
        validity_fixed_until=dt(2023, 2, 9, 12, 15, 0),
    )
    assert i.compute_validity(requested_start=dt(2024, 1, 1, 0, 0, 0), override_tz=tz) == (None, None)
