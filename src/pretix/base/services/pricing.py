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
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from itertools import groupby
from typing import List, Literal, Optional, Tuple, Union

from django import forms
from django.conf import settings
from django.db.models import Q

from pretix.base.decimal import round_decimal
from pretix.base.models import (
    AbstractPosition, CartPosition, InvoiceAddress, Item, ItemAddOn,
    ItemVariation, OrderFee, OrderPosition, SalesChannel, Voucher,
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
                                 override_tax_code=price.code,
                                 invoice_address=invoice_address, subtract_from_gross=bundled_sum)
        else:
            price = tax_rule.tax(max(custom_price, price.gross), base_price_is='gross', override_tax_rate=price.rate,
                                 override_tax_code=price.code,
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
                   tax_rule: TaxRule, invoice_address: InvoiceAddress, bundled_sum: Decimal,
                   is_bundled=False) -> TaxedPrice:
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
                                 override_tax_code=price.code, invoice_address=invoice_address,
                                 subtract_from_gross=bundled_sum)
        else:
            price = tax_rule.tax(max(custom_price_input, price.gross), base_price_is='gross',
                                 override_tax_rate=price.rate,
                                 override_tax_code=price.code, invoice_address=invoice_address,
                                 subtract_from_gross=bundled_sum)
    else:
        price = tax_rule.tax(price_after_voucher, invoice_address=invoice_address, subtract_from_gross=bundled_sum,
                             base_price_is='gross' if is_bundled else 'auto')

    return price


def apply_discounts(event: Event, sales_channel: Union[str, SalesChannel],
                    positions: List[Tuple[int, Optional[int], Optional[datetime], Decimal, bool, bool, Decimal]],
                    collect_potential_discounts: Optional[defaultdict] = None) -> List[Tuple[Decimal, Optional[Discount]]]:
    """
    Applies any dynamic discounts to a cart

    :param event: Event the cart belongs to
    :param sales_channel: Sales channel the cart was created with
    :param positions: Tuple of the form ``(item_id, subevent_id, subevent_date_from, line_price_gross, addon_to_id, is_bundled, voucher_discount)``
                      ``addon_to_id`` does not have to be the proper ID, any identifier is okay, even ``True``/``False`` are accepted, but
                      a better result may be given if addons to the same main product have the same distinct value.
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
            idx: PositionInfo(item_id, subevent_id, subevent_date_from, line_price_gross, addon_to, voucher_discount)
            for
            idx, (item_id, subevent_id, subevent_date_from, line_price_gross, addon_to, is_bundled, voucher_discount)
            in enumerate(positions)
            if not is_bundled and idx not in new_prices
        }, collect_potential_discounts)
        for k in result.keys():
            result[k] = (result[k], discount)
        new_prices.update(result)

    return [new_prices.get(idx, (p[3], None)) for idx, p in enumerate(positions)]


def apply_rounding(rounding_mode: Literal["line", "sum_by_net", "sum_by_net_only_business", "sum_by_net_keep_gross"],
                   invoice_address: Optional[InvoiceAddress], currency: str,
                   lines: List[Union[OrderPosition, CartPosition, OrderFee]]) -> list:
    """
    Given a list of order positions / cart positions / order fees (may be mixed), applies the given rounding mode
    and mutates the ``price``, ``price_includes_rounding_correction``, ``tax_value``, and
    ``tax_value_includes_rounding_correction`` attributes.

    When rounding mode is set to ``"line"``, the tax will be computed and rounded individually for every line.

    When rounding mode is set to ``"sum_by_net_keep_gross"``, the tax values of the individual lines will be adjusted
    such that the per-taxrate/taxcode subtotal is rounded correctly. The gross prices will stay constant.

    When rounding mode is set to ``"sum_by_net"``, the gross prices and tax values of the individual lines will be
    adjusted such that the per-taxrate/taxcode subtotal is rounded correctly. The net prices will stay constant.

    :param rounding_mode: One of ``"line"``, ``"sum_by_net"``, ``"sum_by_net_only_business"``, or ``"sum_by_net_keep_gross"``.
    :param invoice_address: The invoice address, or ``None``
    :param currency: Currency that will be used to determine rounding precision
    :param lines: List of order/cart contents
    :return: Collection of ``lines`` members that have been changed and may need to be persisted to the database.
    """
    if rounding_mode == "sum_by_net_only_business":
        if invoice_address and invoice_address.is_business:
            rounding_mode = "sum_by_net"
        else:
            rounding_mode = "line"

    def _key(line):
        return (line.tax_rate, line.tax_code or "")

    places = settings.CURRENCY_PLACES.get(currency, 2)
    minimum_unit = Decimal('1') / 10 ** places
    changed = []

    if rounding_mode == "sum_by_net":
        for (tax_rate, tax_code), lines in groupby(sorted(lines, key=_key), key=_key):
            lines = list(sorted(lines, key=lambda l: -l.gross_price_before_rounding))

            # Compute the net and gross total of the line-based computation method
            net_total = sum(l.net_price_before_rounding for l in lines)
            gross_total = sum(l.gross_price_before_rounding for l in lines)

            # Compute the gross total we need to achieve based on the net total
            target_gross_total = round_decimal((net_total * (1 + tax_rate / 100)), currency)

            # Add/subtract the smallest possible from both gross prices and tax values (so net values stay the same)
            # until the values align
            diff = target_gross_total - gross_total
            diff_sgn = -1 if diff < 0 else 1
            for l in lines:
                if diff:
                    apply_diff = diff_sgn * minimum_unit
                    l.price = l.gross_price_before_rounding + apply_diff
                    l.price_includes_rounding_correction = apply_diff
                    l.tax_value = l.tax_value_before_rounding + apply_diff
                    l.tax_value_includes_rounding_correction = apply_diff
                    diff -= apply_diff
                    changed.append(l)
                elif l.price_includes_rounding_correction or l.tax_value_includes_rounding_correction:
                    l.price = l.gross_price_before_rounding
                    l.price_includes_rounding_correction = Decimal("0.00")
                    l.tax_value = l.tax_value_before_rounding
                    l.tax_value_includes_rounding_correction = Decimal("0.00")
                    changed.append(l)

    elif rounding_mode == "sum_by_net_keep_gross":
        for (tax_rate, tax_code), lines in groupby(sorted(lines, key=_key), key=_key):
            lines = list(sorted(lines, key=lambda l: -l.gross_price_before_rounding))

            # Compute the net and gross total of the line-based computation method
            net_total = sum(l.net_price_before_rounding for l in lines)
            gross_total = sum(l.gross_price_before_rounding for l in lines)

            # Compute the net total that would yield the correct gross total (if possible)
            target_net_total = round_decimal(gross_total - (gross_total * (1 - 100 / (100 + tax_rate))), currency)

            # Compute the gross total that would be computed from that net total – this will be different than
            # gross_total when there is no possible net value for the gross total
            # e.g. 99.99 at 19% is impossible since 84.03 + 19% = 100.00 and 84.02 + 19% = 99.98
            target_gross_total = round_decimal((target_net_total * (1 + tax_rate / 100)), currency)

            diff_gross = target_gross_total - gross_total
            diff_net = target_net_total - net_total
            diff_gross_sgn = -1 if diff_gross < 0 else 1
            diff_net_sgn = -1 if diff_net < 0 else 1
            for l in lines:
                if diff_gross:
                    apply_diff = diff_gross_sgn * minimum_unit
                    l.price = l.gross_price_before_rounding + apply_diff
                    l.price_includes_rounding_correction = apply_diff
                    l.tax_value = l.tax_value_before_rounding + apply_diff
                    l.tax_value_includes_rounding_correction = apply_diff
                    changed.append(l)
                    diff_gross -= apply_diff
                elif diff_net:
                    apply_diff = diff_net_sgn * minimum_unit
                    l.price = l.gross_price_before_rounding
                    l.price_includes_rounding_correction = Decimal("0.00")
                    l.tax_value = l.tax_value_before_rounding - apply_diff
                    l.tax_value_includes_rounding_correction = -apply_diff
                    changed.append(l)
                    diff_net -= apply_diff
                elif l.price_includes_rounding_correction or l.tax_value_includes_rounding_correction:
                    l.price = l.gross_price_before_rounding
                    l.price_includes_rounding_correction = Decimal("0.00")
                    l.tax_value = l.tax_value_before_rounding
                    l.tax_value_includes_rounding_correction = Decimal("0.00")
                    changed.append(l)

    elif rounding_mode == "line":
        for l in lines:
            if l.price_includes_rounding_correction or l.tax_value_includes_rounding_correction:
                l.price = l.gross_price_before_rounding
                l.price_includes_rounding_correction = Decimal("0.00")
                l.tax_value = l.tax_value_before_rounding
                l.tax_value_includes_rounding_correction = Decimal("0.00")
                changed.append(l)

    else:
        raise ValueError("Unknown rounding_mode")

    return changed
