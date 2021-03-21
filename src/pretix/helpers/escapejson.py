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
from django.utils.encoding import force_str
from django.utils.functional import keep_lazy
from django.utils.safestring import SafeText, mark_safe

_json_escapes = {
    ord('>'): '\\u003E',
    ord('<'): '\\u003C',
    ord('&'): '\\u0026',
}

_json_escapes_attr = {
    ord('>'): '\\u003E',
    ord('<'): '\\u003C',
    ord('&'): '\\u0026',
    ord('"'): '&#34;',
    ord("'"): '&#39;',
    ord("="): '&#61;',
}


@keep_lazy(str, SafeText)
def escapejson(value):
    """Hex encodes characters for use in a application/json type script."""
    return mark_safe(force_str(value).translate(_json_escapes))


@keep_lazy(str, SafeText)
def escapejson_attr(value):
    """Hex encodes characters for use in a html attributw script."""
    return mark_safe(force_str(value).translate(_json_escapes_attr))
