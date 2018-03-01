from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings


def round_decimal(dec, currency=None):
    if currency:
        places = settings.CURRENCY_PLACES.get(currency, 2)
        return Decimal(dec).quantize(
            Decimal('1') / 10 ** places, ROUND_HALF_UP
        )
    return Decimal(dec).quantize(Decimal('0.01'), ROUND_HALF_UP)
