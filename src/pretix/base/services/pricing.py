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
import re
from collections import defaultdict
from decimal import Decimal
from typing import List, Optional, Tuple, Union

from django import forms
from django.db.models import Q

from pretix.base.decimal import round_decimal
from pretix.base.models import (
    AbstractPosition, InvoiceAddress, Item, ItemAddOn, ItemVariation,
    SalesChannel, Voucher,
)
from pretix.base.models.discount import Discount, PositionInfo
from pretix.base.models.event import Event, SubEvent
from pretix.base.models.tax import TAXED_ZERO, TaxedPrice, TaxRule
from pretix.base.timemachine import time_machine_now


def get_price(item: Item, variation: ItemVariation = None,
              voucher: Voucher = None, custom_price: Decimal = None,
              subevent: SubEvent = None, custom_price_is_net: bool = False,
              custom_price_is_tax_rate: Decimal = None,
              addon_to: AbstractPosition = None, invoice_address: InvoiceAddress = None,
              force_custom_price: bool = False, bundled_sum: Decimal = Decimal('0.00'),
              max_discount: Decimal = None, tax_rule=None) -> TaxedPrice:
    if is_included_for_free(item, addon_to):
        return TAXED_ZERO

    price = get_listed_price(item, variation, subevent)

    if voucher:
        price = voucher.calculate_price(price, max_discount=max_discount)

    if tax_rule is not None:
        tax_rule = tax_rule
    elif item.tax_rule:
        tax_rule = item.tax_rule
    else:
        tax_rule = TaxRule(
            name='',
            rate=Decimal('0.00'),
            price_includes_tax=True,
            eu_reverse_charge=False,
        )

    if force_custom_price and custom_price is not None and custom_price != "":
        if custom_price_is_net:
            price = tax_rule.tax(custom_price, base_price_is='net', invoice_address=invoice_address,
                                 subtract_from_gross=bundled_sum)
        else:
            price = tax_rule.tax(custom_price, base_price_is='gross', invoice_address=invoice_address,
                                 subtract_from_gross=bundled_sum)
    elif item.free_price and custom_price is not None and custom_price != "":
        if not isinstance(custom_price, Decimal):
            custom_price = re.sub('[^0-9.,]', '', str(custom_price))
            if not custom_price:
                raise ValueError('price_not_a_number')
            try:
                custom_price = forms.DecimalField(localize=True).to_python(custom_price)
            except:
                try:
                    custom_price = Decimal(custom_price)
                except:
                    raise ValueError('price_not_a_number')
        if custom_price > 99_999_999_999:
            raise ValueError('price_too_high')

        price = tax_rule.tax(price, invoice_address=invoice_address)

        if custom_price_is_net:
            price = tax_rule.tax(max(custom_price, price.net), base_price_is='net', override_tax_rate=price.rate,
                                 invoice_address=invoice_address, subtract_from_gross=bundled_sum)
        else:
            price = tax_rule.tax(max(custom_price, price.gross), base_price_is='gross', override_tax_rate=price.rate,
                                 invoice_address=invoice_address, subtract_from_gross=bundled_sum)
    else:
        price = tax_rule.tax(price, invoice_address=invoice_address, subtract_from_gross=bundled_sum)

    price.gross = round_decimal(price.gross, item.event.currency)
    price.net = round_decimal(price.net, item.event.currency)
    price.tax = price.gross - price.net

    return price


def is_included_for_free(item: Item, addon_to: AbstractPosition):
    if addon_to:
        try:
            iao = addon_to.item.addons.get(addon_category_id=item.category_id)
            if iao.price_included:
                return True
        except ItemAddOn.DoesNotExist:
            pass
        if addon_to.voucher_id and addon_to.voucher.all_addons_included:
            return True
    return False


def get_listed_price(item: Item, variation: ItemVariation = None, subevent: SubEvent = None) -> Decimal:
    price = item.default_price
    if subevent and item.pk in subevent.item_price_overrides:
        price = subevent.item_price_overrides[item.pk]

    if variation is not None:
        if variation.default_price is not None:
            price = variation.default_price
        if subevent and variation.pk in subevent.var_price_overrides:
            price = subevent.var_price_overrides[variation.pk]

    return price


def get_line_price(price_after_voucher: Decimal, custom_price_input: Decimal, custom_price_input_is_net: bool,
                   tax_rule: TaxRule, invoice_address: InvoiceAddress, bundled_sum: Decimal, is_bundled=False) -> TaxedPrice:
    if not tax_rule:
        tax_rule = TaxRule(
            name='',
            rate=Decimal('0.00'),
            price_includes_tax=True,
            eu_reverse_charge=False,
        )
    if custom_price_input:
        price = tax_rule.tax(price_after_voucher, invoice_address=invoice_address)

        if custom_price_input_is_net:
            price = tax_rule.tax(max(custom_price_input, price.net), base_price_is='net', override_tax_rate=price.rate,
                                 invoice_address=invoice_address, subtract_from_gross=bundled_sum)
        else:
            price = tax_rule.tax(max(custom_price_input, price.gross), base_price_is='gross', override_tax_rate=price.rate,
                                 invoice_address=invoice_address, subtract_from_gross=bundled_sum)
    else:
        price = tax_rule.tax(price_after_voucher, invoice_address=invoice_address, subtract_from_gross=bundled_sum,
                             base_price_is='gross' if is_bundled else 'auto')

    return price


def apply_discounts(event: Event, sales_channel: Union[str, SalesChannel],
                    positions: List[Tuple[int, Optional[int], Decimal, bool, bool, Decimal]],
                    collect_potential_discounts: Optional[defaultdict]=None) -> List[Tuple[Decimal, Optional[Discount]]]:
    """
    Applies any dynamic discounts to a cart

    :param event: Event the cart belongs to
    :param sales_channel: Sales channel the cart was created with
    :param positions: Tuple of the form ``(item_id, subevent_id, line_price_gross, is_addon_to, is_bundled, voucher_discount)``
    :param collect_potential_discounts: If a `defaultdict(list)` is supplied, all discounts that could be applied to the cart
    based on the "consumed" items, but lack matching "benefitting" items will be collected therein.
    The dict will contain a mapping from index in the `positions` list of the item that could be consumed, to a list
    of tuples describing the discounts that could be applied in the form `(discount, max_count, grouping_id)`.
    `max_count` is either the maximum number of benefitting items that the discount would apply to, or `inf` if that number
    is not limited. The `grouping_id` can be used to distinguish several occurrences of the same discount.

    :return: A list of ``(new_gross_price, discount)`` tuples in the same order as the input
    """
    if isinstance(sales_channel, SalesChannel):
        sales_channel = sales_channel.identifier
    new_prices = {}

    discount_qs = event.discounts.filter(
        Q(available_from__isnull=True) | Q(available_from__lte=time_machine_now()),
        Q(available_until__isnull=True) | Q(available_until__gte=time_machine_now()),
        Q(all_sales_channels=True) | Q(limit_sales_channels__identifier=sales_channel),
        active=True,
    ).prefetch_related('condition_limit_products', 'benefit_limit_products').order_by('position', 'pk')
    for discount in discount_qs:
        result = discount.apply({
            idx: PositionInfo(item_id, subevent_id, line_price_gross, is_addon_to, voucher_discount)
            for idx, (item_id, subevent_id, line_price_gross, is_addon_to, is_bundled, voucher_discount) in enumerate(positions)
            if not is_bundled and idx not in new_prices
        }, collect_potential_discounts)
        for k in result.keys():
            result[k] = (result[k], discount)
        new_prices.update(result)

    return [new_prices.get(idx, (p[2], None)) for idx, p in enumerate(positions)]
