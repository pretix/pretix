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
from decimal import ROUND_HALF_UP, Decimal

from babel.numbers import format_currency
from django import template
from django.conf import settings
from django.template.defaultfilters import floatformat
from django.utils import translation

register = template.Library()


@register.filter("money")
def money_filter(value: Decimal, arg='', hide_currency=False):
    if isinstance(value, (float, int)):
        value = Decimal(value)
    if value is None:
        value = Decimal('0.00')
    if not isinstance(value, Decimal):
        if value == '':
            return value
        raise TypeError("Invalid data type passed to money filter: %r" % type(value))
    if not arg:
        raise ValueError("No currency passed.")
    arg = arg.upper()

    places = settings.CURRENCY_PLACES.get(arg, 2)
    rounded = value.quantize(Decimal('1') / 10 ** places, ROUND_HALF_UP)
    if places < 2 and rounded != value:
        places = 2
    if hide_currency:
        return floatformat(value, places)

    try:
        if rounded != value:
            # We display decimal places even if we shouldn't for this currency if rounding
            # would make the numbers incorrect. If this branch executes, it's likely a bug in
            # pretix, but we won't show wrong numbers!
            return '{} {}'.format(
                arg,
                floatformat(value, 2)
            )
        return format_currency(value, arg, locale=translation.get_language()[:2])
    except:
        return '{} {}'.format(
            arg,
            floatformat(value, places)
        )


@register.filter("money_numberfield")
def money_numberfield_filter(value: Decimal, arg=''):
    if isinstance(value, (float, int)):
        value = Decimal(value)
    if not isinstance(value, Decimal):
        raise TypeError("Invalid data type passed to money filter: %r" % type(value))
    if not arg:
        raise ValueError("No currency passed.")

    places = settings.CURRENCY_PLACES.get(arg, 2)
    return str(value.quantize(Decimal('1') / 10 ** places, ROUND_HALF_UP))
