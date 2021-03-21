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
from datetime import date

from pretix.plugins.banktransfer.tasks import parse_date


def test_date_formats():
    dt = date(year=2020, month=7, day=1)
    assert dt == parse_date("01.07.2020")
    assert dt == parse_date("01.07.20")
    assert dt == parse_date("1.7.2020")
    assert dt == parse_date("1.7.20")

    assert dt == parse_date("07/01/2020")
    assert dt == parse_date("07/01/20")
    assert dt == parse_date("7/1/2020")
    assert dt == parse_date("7/1/20")

    assert dt == parse_date("2020/07/01")

    assert dt == parse_date("2020-07-01")
    assert dt == parse_date("2020-7-1")
