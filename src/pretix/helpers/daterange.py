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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Alvaro Enrique Ruano
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import get_language, pgettext_lazy

from pretix.helpers.templatetags.date_fast import date_fast as _date


def daterange(df, dt, as_html=False):
    lng = get_language()
    if df.year == dt.year and df.month == dt.month and df.day == dt.day:
        if as_html:
            base_format = format_html("<time datetime=\"{}\">{{}}</time>", _date(df, "Y-m-d"))
        else:
            base_format = "{}"
    else:
        if as_html:
            base_format = format_html("<time datetime=\"{}\">{{}}</time>{{}}<time datetime=\"{}\">{{}}</time>", _date(df, "Y-m-d"), _date(dt, "Y-m-d"))
            until = format_html(
                " <span aria-hidden=\"true\">–</span><span class=\"sr-only\"> {until} </span> ",
                until=pgettext_lazy("timerange", "until")
            )
        else:
            base_format = "{}{}{}"
            until = " – "

    if lng.startswith("de"):
        if df.year == dt.year and df.month == dt.month and df.day == dt.day:
            return format_html(base_format, _date(df, "D, j. F Y"))
        elif df.year == dt.year and df.month == dt.month:
            return format_html(base_format, _date(df, "j."), mark_safe(until.strip()), _date(dt, "j. F Y"))
        elif df.year == dt.year:
            return format_html(base_format, _date(df, "j. F"), until, _date(dt, "j. F Y"))
    elif lng == "en-nz":
        if df.year == dt.year and df.month == dt.month and df.day == dt.day:
            # Mon, 15 January 2024
            return format_html(base_format, _date(df, "D, j F Y"))
        elif df.year == dt.year and df.month == dt.month:
            # 1 – 3 January 2024
            return format_html(base_format, _date(df, "j"), until, _date(dt, "j F Y"))
        elif df.year == dt.year:
            # 1 January – 3 April 2024
            return format_html(base_format, _date(df, "j F"), until, _date(dt, "j F Y"))
    elif lng.startswith("en"):
        if df.year == dt.year and df.month == dt.month and df.day == dt.day:
            return format_html(base_format, _date(df, "D, N j, Y"))
        elif df.year == dt.year and df.month == dt.month:
            return format_html(base_format, _date(df, "N j"), until, _date(dt, "j, Y"))
        elif df.year == dt.year:
            return format_html(base_format, _date(df, "N j"), until, _date(dt, "N j, Y"))
    elif lng.startswith("es"):
        if df.year == dt.year and df.month == dt.month and df.day == dt.day:
            return format_html(base_format, _date(df, "DATE_FORMAT"))
        elif df.year == dt.year and df.month == dt.month:
            return format_html(
                base_format,
                _date(df, "j"),
                until,
                "{} de {} de {}".format(_date(dt, "j"), _date(dt, "F"), _date(dt, "Y"))
            )
        elif df.year == dt.year:
            return format_html(
                base_format,
                "{} de {}".format(_date(df, "j"), _date(df, "F")),
                until,
                "{} de {} de {}".format(_date(dt, "j"), _date(dt, "F"), _date(dt, "Y"))
            )

    if df.year == dt.year and df.month == dt.month and df.day == dt.day:
        return format_html(base_format, _date(df, "DATE_FORMAT"))

    if as_html:
        base_format = "<time datetime=\"{}\">{}</time>"
        return format_html(
            "{date_from}{until}{date_to}",
            date_from=format_html(base_format, _date(df, "Y-m-d"), _date(df, "DATE_FORMAT")),
            date_to=format_html(base_format, _date(dt, "Y-m-d"), _date(dt, "DATE_FORMAT")),
            until=until,
        )

    return "{date_from}{until}{date_to}".format(
        date_from=_date(df, "DATE_FORMAT"),
        date_to=_date(dt, "DATE_FORMAT"),
        until=until,
    )


def datetimerange(df, dt, as_html=False):
    if as_html:
        base_format = format_html("<time datetime=\"{}\">{{}}</time>{{}}<time datetime=\"{}\">{{}}</time>", _date(df, "Y-m-d H:i"), _date(dt, "Y-m-d H:i"))
        until = format_html(
            " <span aria-hidden=\"true\">–</span><span class=\"sr-only\"> {until} </span> ",
            until=pgettext_lazy("timerange", "until")
        )
    else:
        base_format = "{}{}{}"
        until = " – "

    if df.year == dt.year and df.month == dt.month and df.day == dt.day:
        return format_html(base_format, _date(df, "SHORT_DATE_FORMAT") + " " + _date(df, "TIME_FORMAT"), until, _date(dt, "TIME_FORMAT"))
    else:
        return format_html(base_format, _date(df, "SHORT_DATETIME_FORMAT"), until, _date(dt, "SHORT_DATETIME_FORMAT"))
