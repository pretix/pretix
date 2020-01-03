from decimal import Decimal

from pretix.base.decimal import round_decimal
from pretix.base.models import (
    AbstractPosition, InvoiceAddress, Item, ItemAddOn, ItemVariation, Voucher,
)
from pretix.base.models.event import SubEvent
from pretix.base.models.tax import TAXED_ZERO, TaxedPrice, TaxRule


def get_price(item: Item, variation: ItemVariation = None,
              voucher: Voucher = None, custom_price: Decimal = None,
              subevent: SubEvent = None, custom_price_is_net: bool = False,
              addon_to: AbstractPosition = None, invoice_address: InvoiceAddress = None,
              force_custom_price: bool = False, bundled_sum: Decimal = Decimal('0.00'),
              max_discount: Decimal = None) -> TaxedPrice:
    if addon_to:
        try:
            iao = addon_to.item.addons.get(addon_category_id=item.category_id)
            if iao.price_included:
                return TAXED_ZERO
        except ItemAddOn.DoesNotExist:
            pass

    price = item.default_price
    if subevent and item.pk in subevent.item_price_overrides:
        price = subevent.item_price_overrides[item.pk]

    if variation is not None:
        if variation.default_price is not None:
            price = variation.default_price
        if subevent and variation.pk in subevent.var_price_overrides:
            price = subevent.var_price_overrides[variation.pk]

    if voucher:
        price = voucher.calculate_price(price, max_discount=max_discount)

    if item.tax_rule:
        tax_rule = item.tax_rule
    else:
        tax_rule = TaxRule(
            name='',
            rate=Decimal('0.00'),
            price_includes_tax=True,
            eu_reverse_charge=False,
        )
    price = tax_rule.tax(price)

    if force_custom_price and custom_price is not None and custom_price != "":
        if custom_price_is_net:
            price = tax_rule.tax(custom_price, base_price_is='net')
        else:
            price = tax_rule.tax(custom_price, base_price_is='gross')
    if item.free_price and custom_price is not None and custom_price != "":
        if not isinstance(custom_price, Decimal):
            custom_price = Decimal(str(custom_price).replace(",", "."))
        if custom_price > 100000000:
            raise ValueError('price_too_high')
        if custom_price_is_net:
            price = tax_rule.tax(max(custom_price, price.net), base_price_is='net')
        else:
            price = tax_rule.tax(max(custom_price, price.gross), base_price_is='gross')

    if bundled_sum:
        price = price - TaxedPrice(net=bundled_sum, gross=bundled_sum, rate=0, tax=0, name='')
        if price.gross < Decimal('0.00'):
            return TAXED_ZERO

    if invoice_address and not tax_rule.tax_applicable(invoice_address):
        price.tax = Decimal('0.00')
        price.rate = Decimal('0.00')
        price.gross = price.net
        price.name = ''

    price.gross = round_decimal(price.gross, item.event.currency)
    price.net = round_decimal(price.net, item.event.currency)
    price.tax = price.gross - price.net

    return price
