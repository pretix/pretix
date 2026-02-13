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
from decimal import Decimal

import pytest

from pretix.base.models import InvoiceAddress, OrderPosition, TaxRule
from pretix.base.services.pricing import apply_rounding


@pytest.fixture
def sample_lines():
    lines = [OrderPosition(
        price=Decimal("100.00"),
        tax_value=Decimal("15.97"),
        tax_rate=Decimal("19.00"),
        tax_code="S",
    ) for _ in range(5)]
    return lines


def _validate_sample_lines(sample_lines, rounding_mode):
    corrections = [
        (line.tax_value_includes_rounding_correction, line.price_includes_rounding_correction)
        for line in sample_lines
    ]
    changed = apply_rounding(rounding_mode, None, "EUR", sample_lines)
    for line, original in zip(sample_lines, corrections):
        if (line.tax_value_includes_rounding_correction, line.price_includes_rounding_correction) != original:
            assert line in changed
        else:
            assert line not in changed

    if rounding_mode == "line":
        for line in sample_lines:
            assert line.price == Decimal("100.00")
            assert line.tax_value == Decimal("15.97")
            assert line.tax_rate == Decimal("19.00")
        assert sum(line.price for line in sample_lines) == Decimal("500.00")
        assert sum(line.tax_value for line in sample_lines) == Decimal("79.85")
    elif rounding_mode == "sum_by_net":
        for line in sample_lines:
            # gross price may vary
            assert line.price - line.tax_value == Decimal("84.03")
            assert line.tax_rate == Decimal("19.00")
        assert sum(line.price for line in sample_lines) == Decimal("499.98")
        assert sum(line.tax_value for line in sample_lines) == Decimal("79.83")
        assert sum(line.price - line.tax_value for line in sample_lines) == Decimal("420.15")
    elif rounding_mode == "sum_by_net_keep_gross":
        for line in sample_lines:
            assert line.price == Decimal("100.00")
            # net price may vary
            assert line.tax_rate == Decimal("19.00")
        assert sum(line.price for line in sample_lines) == Decimal("500.00")
        assert sum(line.tax_value for line in sample_lines) == Decimal("79.83")
        assert sum(line.price - line.tax_value for line in sample_lines) == Decimal("420.17")


@pytest.mark.django_db
def test_simple_case_by_line(sample_lines):
    _validate_sample_lines(sample_lines, "line")


@pytest.mark.django_db
def test_simple_case_by_net(sample_lines):
    _validate_sample_lines(sample_lines, "sum_by_net")


@pytest.mark.django_db
def test_simple_case_by_gross(sample_lines):
    _validate_sample_lines(sample_lines, "sum_by_net_keep_gross")


@pytest.mark.django_db
def test_simple_case_switch_rounding(sample_lines):
    _validate_sample_lines(sample_lines, "sum_by_net")
    _validate_sample_lines(sample_lines, "sum_by_net_keep_gross")
    _validate_sample_lines(sample_lines, "line")
    _validate_sample_lines(sample_lines, "sum_by_net")


@pytest.mark.django_db
def test_revert_net_rounding_to_single_line(sample_lines):
    l = OrderPosition(
        price=Decimal("100.01"),
        price_includes_rounding_correction=Decimal("0.01"),
        tax_value=Decimal("15.98"),
        tax_value_includes_rounding_correction=Decimal("0.01"),
        tax_rate=Decimal("19.00"),
        tax_code="S",
    )
    apply_rounding("sum_by_net", None, "EUR", [l])
    assert l.price == Decimal("100.00")
    assert l.price_includes_rounding_correction == Decimal("0.00")
    assert l.tax_value == Decimal("15.97")
    assert l.tax_value_includes_rounding_correction == Decimal("0.00")
    assert l.tax_rate == Decimal("19.00")


@pytest.mark.django_db
def test_revert_net_keep_gross_rounding_to_single_line(sample_lines):
    l = OrderPosition(
        price=Decimal("100.00"),
        price_includes_rounding_correction=Decimal("0.00"),
        tax_value=Decimal("15.96"),
        tax_value_includes_rounding_correction=Decimal("-0.01"),
        tax_rate=Decimal("19.00"),
        tax_code="S",
    )
    apply_rounding("sum_by_net_keep_gross", None, "EUR", [l])
    assert l.price == Decimal("100.00")
    assert l.price_includes_rounding_correction == Decimal("0.00")
    assert l.tax_value == Decimal("15.97")
    assert l.tax_value_includes_rounding_correction == Decimal("0.00")
    assert l.tax_rate == Decimal("19.00")


@pytest.mark.django_db
@pytest.mark.parametrize("rounding_mode", [
    "sum_by_net",
    "sum_by_net_keep_gross",
])
def test_rounding_of_impossible_gross_price(rounding_mode):
    l = OrderPosition(
        price=Decimal("23.00"),
    )
    l._calculate_tax(tax_rule=TaxRule(rate=Decimal("7.00")), invoice_address=InvoiceAddress())
    apply_rounding(rounding_mode, None, "EUR", [l])
    assert l.price == Decimal("23.01")
    assert l.price_includes_rounding_correction == Decimal("0.01")
    assert l.tax_value == Decimal("1.51")
    assert l.tax_value_includes_rounding_correction == Decimal("0.01")
    assert l.tax_rate == Decimal("7.00")


@pytest.mark.django_db
def test_round_down():
    lines = [OrderPosition(
        price=Decimal("100.00"),
        tax_value=Decimal("15.97"),
        tax_rate=Decimal("19.00"),
        tax_code="S",
    ) for _ in range(5)]
    assert sum(l.price for l in lines) == Decimal("500.00")
    assert sum(l.tax_value for l in lines) == Decimal("79.85")
    assert sum(l.price - l.tax_value for l in lines) == Decimal("420.15")

    apply_rounding("sum_by_net", None, "EUR", lines)
    assert sum(l.price for l in lines) == Decimal("499.98")
    assert sum(l.tax_value for l in lines) == Decimal("79.83")
    assert sum(l.price - l.tax_value for l in lines) == Decimal("420.15")

    apply_rounding("sum_by_net_keep_gross", None, "EUR", lines)
    assert sum(l.price for l in lines) == Decimal("500.00")
    assert sum(l.tax_value for l in lines) == Decimal("79.83")
    assert sum(l.price - l.tax_value for l in lines) == Decimal("420.17")


@pytest.mark.django_db
def test_round_up():
    lines = [OrderPosition(
        price=Decimal("99.98"),
        tax_value=Decimal("15.96"),
        tax_rate=Decimal("19.00"),
        tax_code="S",
    ) for _ in range(5)]
    assert sum(l.price for l in lines) == Decimal("499.90")
    assert sum(l.tax_value for l in lines) == Decimal("79.80")
    assert sum(l.price - l.tax_value for l in lines) == Decimal("420.10")

    apply_rounding("sum_by_net", None, "EUR", lines)
    assert sum(l.price for l in lines) == Decimal("499.92")
    assert sum(l.tax_value for l in lines) == Decimal("79.82")
    assert sum(l.price - l.tax_value for l in lines) == Decimal("420.10")

    apply_rounding("sum_by_net_keep_gross", None, "EUR", lines)
    assert sum(l.price for l in lines) == Decimal("499.90")
    assert sum(l.tax_value for l in lines) == Decimal("79.82")
    assert sum(l.price - l.tax_value for l in lines) == Decimal("420.08")


@pytest.mark.django_db
def test_round_currency_without_decimals():
    lines = [OrderPosition(
        price=Decimal("9998.00"),
        tax_value=Decimal("1596.00"),
        tax_rate=Decimal("19.00"),
        tax_code="S",
    ) for _ in range(5)]
    assert sum(l.price for l in lines) == Decimal("49990.00")
    assert sum(l.tax_value for l in lines) == Decimal("7980.00")
    assert sum(l.price - l.tax_value for l in lines) == Decimal("42010.00")

    apply_rounding("sum_by_net", None, "JPY", lines)
    assert sum(l.price for l in lines) == Decimal("49992.00")
    assert sum(l.tax_value for l in lines) == Decimal("7982.00")
    assert sum(l.price - l.tax_value for l in lines) == Decimal("42010.00")

    apply_rounding("sum_by_net_keep_gross", None, "JPY", lines)
    assert sum(l.price for l in lines) == Decimal("49990.00")
    assert sum(l.tax_value for l in lines) == Decimal("7982.00")
    assert sum(l.price - l.tax_value for l in lines) == Decimal("42008.00")


@pytest.mark.django_db
@pytest.mark.parametrize("rounding_mode", [
    "sum_by_net",
    "sum_by_net_keep_gross",
])
def test_do_not_touch_free(rounding_mode):
    l1 = OrderPosition(
        price=Decimal("0.00"),
    )
    l1._calculate_tax(tax_rule=TaxRule(rate=Decimal("7.00")), invoice_address=InvoiceAddress())
    l2 = OrderPosition(
        price=Decimal("23.00"),
    )
    l2._calculate_tax(tax_rule=TaxRule(rate=Decimal("7.00")), invoice_address=InvoiceAddress())
    apply_rounding(rounding_mode, None, "EUR", [l1, l2])
    assert l2.price == Decimal("23.01")
    assert l2.price_includes_rounding_correction == Decimal("0.01")
    assert l2.tax_value == Decimal("1.51")
    assert l2.tax_value_includes_rounding_correction == Decimal("0.01")
    assert l2.tax_rate == Decimal("7.00")
    assert l1.price == Decimal("0.00")
    assert l1.price_includes_rounding_correction == Decimal("0.00")
    assert l1.tax_value == Decimal("0.00")
    assert l1.tax_value_includes_rounding_correction == Decimal("0.00")


@pytest.mark.django_db
def test_only_business():
    lines = [OrderPosition(
        price=Decimal("100.00"),
        tax_value=Decimal("15.97"),
        tax_rate=Decimal("19.00"),
        tax_code="S",
    ) for _ in range(5)]
    assert sum(l.price for l in lines) == Decimal("500.00")

    apply_rounding("sum_by_net_only_business", None, "EUR", lines)
    assert sum(l.price for l in lines) == Decimal("500.00")

    apply_rounding("sum_by_net_only_business", InvoiceAddress(is_business=True), "EUR", lines)
    assert sum(l.price for l in lines) == Decimal("499.98")
