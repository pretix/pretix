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

# Date according to https://docs.djangoproject.com/en/dev/ref/templates/builtins/#date
# Following NZ government guidance from https://www.digital.govt.nz/standards-and-guidance/design-and-ux/content-design-guidance/writing-style/numbers
DATE_FORMAT = "j F Y"              # 12 December 2015
DATETIME_FORMAT = "j F Y, g:ia"    # 12 December 2015, 5:30pm
TIME_FORMAT = "g:ia"               # 5:30pm
YEAR_MONTH_FORMAT = "F Y"          # December 2015
MONTH_DAY_FORMAT = "j F"           # 12 December
SHORT_DATE_FORMAT = "j F Y"        # same as DATE_FORMAT per guidance
SHORT_DATETIME_FORMAT = "j F Y, g:ia"
WEEKDAY_FORMAT = "l"               # Monday
WEEKDAY_DATE_FORMAT = "l, j F Y"   # Friday, 23 November 2018
WEEK_FORMAT = "\\W W, o"          # ISO week: "W 52, 2024"
WEEK_DAY_FORMAT = "D, j M"        # Abbrev weekday and month: "Mon, 5 Feb"
SHORT_MONTH_DAY_FORMAT = "j/n"    # Numeric day/month: "5/2"

# Parsing inputs; keep d/m/Y and ISO
DATE_INPUT_FORMATS = [
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d/%m/%y",
]

TIME_INPUT_FORMATS = [
    "%I:%M%p",   # 5:30pm
    "%H:%M:%S",
    "%H:%M:%S.%f",
    "%H:%M",
]
