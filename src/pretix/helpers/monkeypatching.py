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


def monkeypatch_vobject_performance():
    """
    This works around a performance issue in the unmaintained vobject library which calls
    a very expensive function for every event in a calendar. Since the slow function is
    mostly used to compare timezones to UTC, not to arbitrary other timezones, we can
    add a few early-out optimizations.
    """

    from vobject import icalendar

    old_tzinfo_eq = icalendar.tzinfo_eq
    test_date = datetime(2000, 1, 1)

    def new_tzinfo_eq(tzinfo1, tzinfo2, *args, **kwargs):
        if tzinfo1 is None:
            return tzinfo2 is None
        if tzinfo2 is None:
            return tzinfo1 is None

        n1 = tzinfo1.tzname(test_date)
        n2 = tzinfo2.tzname(test_date)
        if n1 == "UTC" and n2 == "UTC":
            return True
        if n1 == "UTC" or n2 == "UTC":
            return False
        return old_tzinfo_eq(tzinfo1, tzinfo2, *args, **kwargs)

    icalendar.tzinfo_eq = new_tzinfo_eq


def monkeypatch_all_at_ready():
    monkeypatch_vobject_performance()
