from decimal import ROUND_HALF_UP, Decimal

from babel.numbers import format_currency
from django import template
from django.conf import settings
from django.template.defaultfilters import floatformat
from django.utils import translation

register = template.Library()


@register.filter("money")
def money_filter(value: Decimal, arg='', hide_currency=False):
    if isinstance(value, float) or isinstance(value, int):
        value = Decimal(value)
    if not isinstance(value, Decimal):
        raise TypeError("Invalid data type passed to money filter: %r" % type(value))
    if not arg:
        raise ValueError("No currency passed.")

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
        return format_currency(value, arg, locale=translation.get_language())
    except:
        return '{} {}'.format(
            arg,
            floatformat(value, places)
        )


@register.filter("money_numberfield")
def money_numberfield_filter(value: Decimal, arg=''):
    if isinstance(value, float) or isinstance(value, int):
        value = Decimal(value)
    if not isinstance(value, Decimal):
        raise TypeError("Invalid data type passed to money filter: %r" % type(value))
    if not arg:
        raise ValueError("No currency passed.")

    places = settings.CURRENCY_PLACES.get(arg, 2)
    return str(value.quantize(Decimal('1') / 10 ** places, ROUND_HALF_UP))
