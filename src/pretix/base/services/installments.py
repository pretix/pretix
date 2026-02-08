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

from decimal import ROUND_FLOOR, Decimal
from typing import List


def calculate_installment_amounts(total_amount: Decimal, count: int) -> List[Decimal]:
    """
    Calculates the amounts for each installment payment.

        The calculation divides the total amount into `count` installments.
        It uses floor rounding for the base installment amount and adds any
        remainder to the final installment.

        Example: 100.00 / 3 -> [33.33, 33.33, 33.34]

    :param total_amount: The total amount to be split
    :param count: The number of installments
    :return: A list of Decimal amounts
    :raises ValueError: If count is less than 1
    """
    if count < 1:
        raise ValueError("Installment count must be at least 1")

    if count == 1:
        return [total_amount]

    per_installment = (total_amount / count).quantize(Decimal('0.01'), rounding=ROUND_FLOOR)
    installments = [per_installment] * (count - 1)
    last_installment = total_amount - sum(installments)
    installments.append(last_installment)

    return installments
