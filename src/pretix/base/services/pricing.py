from decimal import Decimal

from pretix.base.decimal import round_decimal
from pretix.base.models import Item, ItemVariation, Voucher
from pretix.base.models.event import SubEvent


def get_price(item: Item, variation: ItemVariation = None,
              voucher: Voucher = None, custom_price: Decimal = None,
              subevent: SubEvent = None, custom_price_is_net: bool = False):
    price = item.default_price
    if subevent and item.pk in subevent.item_price_overrides:
        price = subevent.item_price_overrides[item.pk]

    if variation is not None:
        if variation.default_price is not None:
            price = variation.default_price
        if subevent and variation.pk in subevent.var_price_overrides:
            price = subevent.var_price_overrides[variation.pk]

    if voucher:
        price = voucher.calculate_price(price)

    if item.free_price and custom_price is not None and custom_price != "":
        if not isinstance(custom_price, Decimal):
            custom_price = Decimal(str(custom_price).replace(",", "."))
        if custom_price > 100000000:
            raise ValueError('price_too_high')
        if custom_price_is_net:
            custom_price = round_decimal(custom_price * (100 + item.tax_rate) / 100)
        price = max(custom_price, price)

    return price
