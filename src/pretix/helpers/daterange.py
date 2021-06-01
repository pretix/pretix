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

from django.template.defaultfilters import date as _date
from django.utils.html import format_html
from django.utils.translation import get_language, gettext_lazy as _


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
        else:
            base_format = "{}{}{}"

    if lng.startswith("de"):
        if df.year == dt.year and df.month == dt.month and df.day == dt.day:
            return format_html(base_format, _date(df, "j. F Y"))
        elif df.year == dt.year and df.month == dt.month:
            return format_html(base_format, _date(df, "j."), "–", _date(dt, "j. F Y"))
        elif df.year == dt.year:
            return format_html(base_format, _date(df, "j. F"), " – ", _date(dt, "j. F Y"))
    elif lng.startswith("en"):
        if df.year == dt.year and df.month == dt.month and df.day == dt.day:
            return format_html(base_format, _date(df, "N jS, Y"))
        elif df.year == dt.year and df.month == dt.month:
            return format_html(base_format, _date(df, "N jS"), " – ", _date(dt, "jS, Y"))
        elif df.year == dt.year:
            return format_html(base_format, _date(df, "N jS"), " – ", _date(dt, "N jS, Y"))
    elif lng.startswith("es"):
        if df.year == dt.year and df.month == dt.month and df.day == dt.day:
            return format_html(base_format, _date(df, "DATE_FORMAT"))
        elif df.year == dt.year and df.month == dt.month:
            return format_html(base_format, 
                _date(df, "j"), 
                " - ", 
                "{} de {} de {}".format(_date(dt, "j"), _date(dt, "F"), _date(dt, "Y"))
            )
        elif df.year == dt.year:
            return format_html(base_format, 
                "{} de {}".format(_date(df, "j"), _date(df, "F")),
                " - ", 
                "{} de {} de {}".format(_date(dt, "j"), _date(dt, "F"), _date(dt, "Y"))
            )

    if df.year == dt.year and df.month == dt.month and df.day == dt.day:
        return format_html(base_format, _date(df, "DATE_FORMAT"))

    if as_html:
        base_format = "<time datetime=\"{}\">{{}}</time>"
        return format_html("{date_from} – {date_to}",
            date_from=format_html(base_format, _date(df, "Y-m-d"), _date(df, "DATE_FORMAT")),
            date_to=format_html(base_format, _date(dt, "Y-m-d"), _date(dt, "DATE_FORMAT")),
        )

    return _("{date_from} – {date_to}").format(
        date_from=_date(df, "DATE_FORMAT"),
        date_to=_date(dt, "DATE_FORMAT"),
    )
