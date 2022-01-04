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
import functools

from django import template
from django.utils import dateformat
from django.utils.formats import get_format
from django.utils.translation import get_language

register = template.Library()


@functools.lru_cache(maxsize=32)
def _get_format(format_type, lang):
    return get_format(format_type, lang)


@register.filter(expects_localtime=True, is_safe=False)
def date_fast(value, arg=None):
    """
    Slightly quicker version of |date if the filter is called a lot. The speedup is achieved through
    LRU caching for formats.

    Django's built-in |date filter has a caching mechanism if you call it with a named format,
    i.e. ``|date_fast:"SHORT_DATE_FORMAT"`` will only be ~6% faster than ``|date:"SHORT_DATE_FORMAT"``.

    However, Django's built-in caching has a flaw with unnamed formats, therefore ``|date_fast:"Y-m-d"``
    will be ~12% faster than ``|date:"Y-m-d"``.
    """
    if value in (None, ''):
        return ''

    lang = get_language()
    format = _get_format(arg, lang)

    try:
        return dateformat.format(value, format)
    except AttributeError:
        try:
            return format(value, arg)
        except AttributeError:
            return ''
