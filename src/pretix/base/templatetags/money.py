from decimal import Decimal, ROUND_HALF_UP

from django import template
from django.conf import settings
from django.template.defaultfilters import floatformat

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
    if places < 2 and value.quantize(Decimal('1') / 10 ** places, ROUND_HALF_UP) != value:
        places = 2
    if hide_currency:
        return floatformat(value, places)
    return '{} {}'.format(
        arg,
        floatformat(value, places)
    )
