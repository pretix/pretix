from decimal import ROUND_HALF_UP, Decimal


def round_decimal(dec):
    return Decimal(dec).quantize(Decimal('0.01'), ROUND_HALF_UP)
