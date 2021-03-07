#
# This file is part of pretix Community.
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
# ADDITIONAL TERMS: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are applicable
# granting you additional permissions and placing additional restrictions on your usage of this software. Please refer
# to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive this file, see
# <https://pretix.eu/about/en/license>.
#
from datetime import date

from django.utils import translation

from pretix.helpers.daterange import daterange


def test_same_day_german():
    with translation.override('de'):
        df = date(2003, 2, 1)
        assert daterange(df, df) == "1. Februar 2003"


def test_same_day_english():
    with translation.override('en'):
        df = date(2003, 2, 1)
        assert daterange(df, df) == "Feb. 1st, 2003"


def test_same_day_spanish():
    with translation.override('es'):
        df = date(2003, 2, 1)
        assert daterange(df, df) == "1 de Febrero de 2003"


def test_same_month_german():
    with translation.override('de'):
        df = date(2003, 2, 1)
        dt = date(2003, 2, 3)
        assert daterange(df, dt) == "1.–3. Februar 2003"


def test_same_month_english():
    with translation.override('en'):
        df = date(2003, 2, 1)
        dt = date(2003, 2, 3)
        assert daterange(df, dt) == "Feb. 1st – 3rd, 2003"


def test_same_month_spanish():
    with translation.override('es'):
        df = date(2003, 2, 1)
        dt = date(2003, 2, 3)
        assert daterange(df, dt) == "1 - 3 de Febrero de 2003"


def test_same_year_german():
    with translation.override('de'):
        df = date(2003, 2, 1)
        dt = date(2003, 4, 3)
        assert daterange(df, dt) == "1. Februar – 3. April 2003"


def test_same_year_english():
    with translation.override('en'):
        df = date(2003, 2, 1)
        dt = date(2003, 4, 3)
        assert daterange(df, dt) == "Feb. 1st – April 3rd, 2003"


def test_same_year_spanish():
    with translation.override('es'):
        df = date(2003, 2, 1)
        dt = date(2003, 4, 3)
        assert daterange(df, dt) == "1 de Febrero - 3 de Abril de 2003"


def test_different_dates_german():
    with translation.override('de'):
        df = date(2003, 2, 1)
        dt = date(2005, 4, 3)
        assert daterange(df, dt) == "1. Februar 2003 – 3. April 2005"


def test_different_dates_english():
    with translation.override('en'):
        df = date(2003, 2, 1)
        dt = date(2005, 4, 3)
        assert daterange(df, dt) == "Feb. 1, 2003 – April 3, 2005"


def test_different_dates_spanish():
    with translation.override('es'):
        df = date(2003, 2, 1)
        dt = date(2005, 4, 3)
        assert daterange(df, dt) == "1 de Febrero de 2003 – 3 de Abril de 2005"
