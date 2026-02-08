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

import json
from decimal import ROUND_FLOOR, Decimal
from typing import List

from dateutil.relativedelta import relativedelta
from django.db import models, transaction
from django.utils.timezone import now

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import (
    InstallmentPlan, Order, OrderFee, OrderPayment, ScheduledInstallment,
)


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


@transaction.atomic
def create_installment_plan(
    order: Order,
    provider_name: str,
    installments_count: int,
    fee=None,
    info_data=None,
    amount=None,
) -> InstallmentPlan:
    """
    Creates an installment plan for an order.

    :param order: The Order object
    :param provider_name: The identifier of the payment provider
    :param installments_count: Number of installments
    :param fee: Optional payment fee for the first installment
    :param info_data: Optional payment info dict for the first installment
    :param amount: Explicit amount for the installment plan. If None, uses order.total minus payment fees.
                   Use this when multi-use payments (e.g. gift cards) cover part of the order.
    :return: The created InstallmentPlan
    :raises ValueError: If the provider does not support installments
    """
    event = order.event
    provider = event.get_payment_providers().get(provider_name)

    if not provider or not getattr(provider, 'installments_supported', False):
        raise ValueError(f"Provider '{provider_name}' does not support installments or is not active.")

    max_allowed = provider.get_max_installments_for_cart(reference_date=order.datetime)
    if installments_count > max_allowed:
        raise ValueError(
            f"Requested {installments_count} installments exceeds the maximum of {max_allowed} "
            f"allowed based on the event date."
        )

    payment_fees = Decimal('0.00')
    if amount is not None:
        base_total = amount
    else:
        payment_fees = order.fees.filter(fee_type=OrderFee.FEE_TYPE_PAYMENT).aggregate(
            total=models.Sum('value')
        )['total'] or Decimal('0.00')
        base_total = order.total - payment_fees

    amounts = calculate_installment_amounts(base_total, installments_count)

    plan = InstallmentPlan.objects.create(
        order=order,
        payment_provider=provider_name,
        payment_token={},
        total_installments=installments_count,
        installments_paid=0,
        amount_per_installment=amounts[0],
        status=InstallmentPlan.STATUS_ACTIVE
    )

    first_payment_amount = amounts[0] + payment_fees
    payment = order.payments.create(
        state=OrderPayment.PAYMENT_STATE_CREATED,
        provider=provider_name,
        amount=first_payment_amount,
        fee=fee,
        info=json.dumps(info_data) if info_data else '{}',
        process_initiated=False,
        installment_plan=plan
    )

    ScheduledInstallment.objects.create(
        plan=plan,
        installment_number=1,
        amount=first_payment_amount,
        due_date=now(),
        state=ScheduledInstallment.STATE_PENDING,
        payment=payment,
    )

    for i, amount in enumerate(amounts[1:], start=2):
        due_date = now() + relativedelta(months=i - 1)
        ScheduledInstallment.objects.create(
            plan=plan,
            installment_number=i,
            amount=amount,
            due_date=due_date,
            state=ScheduledInstallment.STATE_PENDING
        )

    return plan
