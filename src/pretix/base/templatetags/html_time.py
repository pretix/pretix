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
from datetime import datetime

from django import template
from django.utils.html import format_html
from django.utils.timezone import get_current_timezone

from pretix.base.i18n import LazyExpiresDate
from pretix.helpers.templatetags.date_fast import date_fast

register = template.Library()


@register.simple_tag
def html_time(value: datetime, dt_format: str = "SHORT_DATE_FORMAT", **kwargs):
    """
    Building a <time datetime='{html-datetime}'>{human-readable datetime}</time> html string,
    where the html-datetime as well as the human-readable datetime can be set
    to a value from django's FORMAT_SETTINGS or "format_expires".

    If attr_fmt isn’t provided, it will be set to isoformat.

    Usage example:
    {% html_time event_start "SHORT_DATETIME_FORMAT" %}
    or
    {% html_time event_start "TIME_FORMAT" attr_fmt="H:i" %}
    """
    if value in (None, ''):
        return ''
    value = value.astimezone(get_current_timezone())
    attr_fmt = kwargs["attr_fmt"] if kwargs else None

    try:
        if not attr_fmt:
            date_html = value.isoformat()
        else:
            date_html = date_fast(value, attr_fmt)

        if dt_format == "format_expires":
            date_human = LazyExpiresDate(value)
        else:
            date_human = date_fast(value, dt_format)
        return format_html("<time datetime='{}'>{}</time>", date_html, date_human)
    except AttributeError:
        return ''
