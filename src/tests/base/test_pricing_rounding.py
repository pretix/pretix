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
from decimal import Decimal

import pytest

from pretix.base.models import OrderPosition
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
    apply_rounding(rounding_mode, "EUR", sample_lines)
    if rounding_mode == "line":
        for l in sample_lines:
            assert l.price == Decimal("100.00")
            assert l.tax_value == Decimal("15.97")
            assert l.tax_rate == Decimal("19.00")
        assert sum(l.price for l in sample_lines) == Decimal("500.00")
        assert sum(l.tax_value for l in sample_lines) == Decimal("79.85")
    elif rounding_mode == "sum_by_net":
        for l in sample_lines:
            # gross price may vary
            assert l.price - l.tax_value == Decimal("84.03")
            assert l.tax_rate == Decimal("19.00")
        assert sum(l.price for l in sample_lines) == Decimal("499.98")
        assert sum(l.tax_value for l in sample_lines) == Decimal("79.83")
    elif rounding_mode == "sum_by_gross":
        for l in sample_lines:
            assert l.price == Decimal("100.00")
            # net price may vary
            assert l.tax_rate == Decimal("19.00")
        assert sum(l.price for l in sample_lines) == Decimal("500.00")
        assert sum(l.tax_value for l in sample_lines) == Decimal("79.83")


@pytest.mark.django_db
def test_simple_case_by_line(sample_lines):
    _validate_sample_lines(sample_lines, "line")


@pytest.mark.django_db
def test_simple_case_by_net(sample_lines):
    _validate_sample_lines(sample_lines, "sum_by_net")


@pytest.mark.django_db
def test_simple_case_by_gross(sample_lines):
    _validate_sample_lines(sample_lines, "sum_by_gross")


@pytest.mark.django_db
def test_simple_case_switch_rounding(sample_lines):
    _validate_sample_lines(sample_lines, "sum_by_net")
    _validate_sample_lines(sample_lines, "sum_by_gross")
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
    apply_rounding("sum_by_net", "EUR", [l])
    assert l.price == Decimal("100.00")
    assert l.tax_value == Decimal("15.97")
    assert l.tax_rate == Decimal("19.00")


@pytest.mark.django_db
def test_revert_gross_rounding_to_single_line(sample_lines):
    l = OrderPosition(
        price=Decimal("100.00"),
        price_includes_rounding_correction=Decimal("0.00"),
        tax_value=Decimal("15.96"),
        tax_value_includes_rounding_correction=Decimal("-0.01"),
        tax_rate=Decimal("19.00"),
        tax_code="S",
    )
    apply_rounding("sum_by_gross", "EUR", [l])
    assert l.price == Decimal("100.00")
    assert l.tax_value == Decimal("15.97")
    assert l.tax_rate == Decimal("19.00")
