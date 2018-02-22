from decimal import Decimal

from django import template
from django.conf import settings
from django.template.defaultfilters import floatformat

register = template.Library()


@register.filter("money")
def money_filter(value: Decimal, arg=''):
    if isinstance(value, float) or isinstance(value, int):
        value = Decimal(value)
    if not isinstance(value, Decimal):
        raise TypeError("Invalid data type passed to money filter: %r" % type(value))
    if not arg:
        raise ValueError("No currency passed.")

    return '{} {}'.format(
        arg,
        floatformat(value, settings.CURRENCY_PLACES.get(arg, 2))
    )
