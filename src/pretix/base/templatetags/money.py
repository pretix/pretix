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
from decimal import ROUND_HALF_UP, Decimal

from babel import Locale, UnknownLocaleError
from babel.numbers import format_currency
from django import template
from django.conf import settings
from django.template.defaultfilters import floatformat
from django.utils import formats
from django.utils.safestring import mark_safe

from pretix.base.i18n import get_babel_locale

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

    currency_places = settings.CURRENCY_PLACES.get(arg, 2)
    required_places = -value.normalize().as_tuple().exponent
    render_places = max(currency_places, required_places)

    if hide_currency:
        return floatformat(value, f"{render_places}g")

    try:
        locale = Locale(get_babel_locale())
    except UnknownLocaleError:
        locale = "en"

    try:
        return format_currency(
            value,
            arg,
            locale=locale,
            # We only allow Babel to restrict the digits to the digits by the currency if this does not remove any
            # precision in case we have sub-currency precision (which we shouldn't have in most places, but it's still
            # better than showing wrong data). Note: Weird precision effects can occur after in-database arithmetic
            # on SQLite, since SQLite does not have fixed-decimal computation.
            currency_digits=currency_places >= required_places,
            decimal_quantization=currency_places >= required_places,
        )
    except:
        return '{} {}'.format(arg, floatformat(value, f"{render_places}g"))


@register.filter("money_without_currency")
def money_filter_without_currency(value: Decimal, arg=''):
    return money_filter(value, arg, hide_currency=True)


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


@register.filter(is_safe=True)
def tax_rate_format(number):
    """
    Display a Decimal to its significant decimal places, used for tax rates.
    """
    if isinstance(number, (float, int, str)):
        number = Decimal(number)
    if number is None:
        number = Decimal('0.00')
    if not isinstance(number, Decimal):
        if number == '':
            return number
        raise TypeError("Invalid data type passed to tax rate format filter: %r" % type(number))
    return mark_safe(
        formats.number_format(
            number,
            -number.normalize().as_tuple().exponent,
            use_l10n=True,
            force_grouping=False,
        )
    )
