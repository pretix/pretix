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
from django import template
from django.conf import settings
from django.template.defaultfilters import floatformat
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='togglesum', needs_autoescape=True)
def togglesum_filter(value, arg='EUR', autoescape=True):
    def noop(x):
        return x

    if not value:
        return ''
    if autoescape:
        esc = conditional_escape
    else:
        esc = noop

    places = settings.CURRENCY_PLACES.get(arg, 2)
    return mark_safe('<span class="count">{0}</span><span class="sum-gross">{1}</span><span class="sum-net">{2}</span>'.format(
        esc(value[0] if value[0] != 0 else ''),
        esc(floatformat(value[1], places) if value[0] != 0 or value[1] != 0 else ''),
        esc(floatformat(value[2], places) if value[0] != 0 or value[2] != 0 else '')
    ))
