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

from pretix.base.services.installments import calculate_installment_amounts


class TestInstallmentCalculation:

    @pytest.mark.parametrize("total,count,expected", [
        (Decimal('300.00'), 3, [Decimal('100.00')] * 3),
        (Decimal('100.00'), 3, [Decimal('33.33'), Decimal('33.33'), Decimal('33.34')]),
        (Decimal('10.00'), 3, [Decimal('3.33'), Decimal('3.33'), Decimal('3.34')]),
        (Decimal('100.00'), 2, [Decimal('50.00'), Decimal('50.00')]),
        (Decimal('120.00'), 12, [Decimal('10.00')] * 12),
        (Decimal('0.04'), 3, [Decimal('0.01'), Decimal('0.01'), Decimal('0.02')]),
        (Decimal('100.00'), 1, [Decimal('100.00')]),
    ])
    def test_split(self, total, count, expected):
        amounts = calculate_installment_amounts(total, count)
        assert amounts == expected
        assert sum(amounts) == total

    @pytest.mark.parametrize("count", [0, -1])
    def test_invalid_count_raises(self, count):
        with pytest.raises(ValueError):
            calculate_installment_amounts(Decimal('100.00'), count)
