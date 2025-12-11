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
from django import template

from pretix.helpers.templatetags.date_fast import date_fast

register = template.Library()


@register.filter(expects_localtime=True, is_safe=False)
def html_datetime(value, args=None):
    """
    Building a <time datetime='{html-datetime}'>{human-readable datetime}</time> html string,
    where the html-datetime as well as the human-readable datetime can be set
    to a value from django's formats.py/FORMAT_SETTINGS via comma-separated arguments.

    If only one argument is given, it will be used as the human-readable datetime attribute,
    and the html datetime attribute will be set to the datetime in iso-format.

    Usage example: input_date|html_datetime:"SHORT_DATE_FORMAT,SHORT_DATE_FORMAT"|safe
    """

    if value in (None, '') or args is None:
        return ''
    arg_list = [arg.strip() for arg in args.split(',')]

    try:
        if len(arg_list) == 1:
            date_html = value.isoformat()
            date_human = date_fast(value, arg_list[0])
        elif len(arg_list) == 2:
            date_html = date_fast(value, arg_list[0])
            date_human = date_fast(value, arg_list[1])
        else:
            raise AttributeError
        return f"<time datetime='{date_html}'>{date_human}</time>"
    except AttributeError:
        return ''
