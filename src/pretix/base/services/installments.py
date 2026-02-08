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
import logging
from datetime import timedelta
from decimal import ROUND_FLOOR, Decimal
from typing import List

from dateutil.relativedelta import relativedelta
from django.db import models, transaction
from django.dispatch import receiver
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import (
    InstallmentPlan, Order, OrderFee, OrderPayment, ScheduledInstallment,
)
from pretix.base.signals import periodic_task
from pretix.helpers.periodic import minimum_interval
from pretix.multidomain.urlreverse import build_absolute_uri

logger = logging.getLogger(__name__)


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


@transaction.atomic
def process_single_installment(installment: ScheduledInstallment, send_mail: bool = False) -> bool:
    """
    Processes a single installment payment.

    :param installment: The ScheduledInstallment to process
    :param send_mail: Whether to send a failure notification email (default False)
    :return: True if successful, False otherwise
    """
    plan = installment.plan
    order = plan.order
    event = order.event

    provider = event.get_payment_providers().get(plan.payment_provider)
    if not provider:
        return False

    if not plan.payment_token or plan.payment_token == {}:
        logger.error(
            "Cannot process installment %s for order %s: no payment token available.",
            installment.pk, order.code,
        )
        installment.state = ScheduledInstallment.STATE_FAILED
        installment.failure_reason = "No payment token available"
        installment.processed_at = now()
        installment.save(update_fields=['state', 'failure_reason', 'processed_at'])
        return False

    success = False
    try:
        success = provider.execute_installment(plan, installment)
    except Exception:
        logger.exception(
            "Failed to execute installment %s for order %s",
            installment.pk, order.code,
        )

    if success:
        payment = OrderPayment.objects.create(
            order=order,
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            amount=installment.amount,
            payment_date=now(),
            provider=plan.payment_provider,
            installment_plan=plan
        )

        installment.state = ScheduledInstallment.STATE_PAID
        installment.payment = payment
        installment.processed_at = now()
        installment.save(update_fields=['state', 'payment', 'processed_at'])

        completed = plan.record_successful_payment()

        if completed:
            try:
                provider.revoke_payment_token(plan)
            except Exception:
                logger.warning(
                    "Failed to revoke payment token for completed plan %s",
                    plan.pk,
                )
            plan.payment_token = {}
            plan.save(update_fields=['payment_token'])

    else:
        installment.state = ScheduledInstallment.STATE_FAILED
        installment.save(update_fields=['state'])

        if not plan.grace_period_end:
            days = provider.settings.get('installments_grace_period_days', as_type=int, default=7)
            plan.grace_period_end = now() + timedelta(days=days)
            plan.save(update_fields=['grace_period_end'])

        if send_mail:
            with language(order.locale, event.settings.region):
                context = get_email_context(event=event, order=order)
                context.update({
                    'failure_reason': installment.failure_reason or '',
                    'expire_date': plan.grace_period_end,
                    'url': build_absolute_uri(
                        event, 'presale:event.order.installment.recovery',
                        kwargs={'order': order.code, 'secret': order.secret}
                    ),
                })
                try:
                    order.send_mail(
                        event.settings.mail_subject_installment_failed,
                        event.settings.mail_text_installment_failed,
                        context,
                        'pretix.event.order.installment.failed',
                    )
                except Exception:
                    logger.warning(
                        "Failed to send installment failure email for order %s",
                        order.code,
                    )

    return success


def process_due_installments():
    """
    Processes all scheduled installments that are due and pending.
    """
    qs = ScheduledInstallment.objects.filter(
        state=ScheduledInstallment.STATE_PENDING,
        due_date__lte=now()
    ).select_related('plan', 'plan__order', 'plan__order__event')

    for installment in qs:
        try:
            process_single_installment(installment, send_mail=True)
        except Exception:
            logger.exception(
                "Error processing installment %s for order %s",
                installment.pk, installment.plan.order.code,
            )


def process_expired_plans():
    """
    Processes all installment plans where the grace period has expired.
    Cancels the order and sends notification emails.
    """
    qs = InstallmentPlan.objects.filter(
        status=InstallmentPlan.STATUS_ACTIVE,
        grace_period_end__lt=now()
    ).select_related('order', 'order__event')

    for plan in qs:
        try:
            order = plan.order
            event = order.event

            cancel_installment_plan(plan, cancel_order=True, user=None, log=True, send_mail=False)

            with language(order.locale, event.settings.region):
                email_subject = event.settings.mail_subject_installment_cancelled
                email_template = event.settings.mail_text_installment_cancelled

                context = get_email_context(event=event, order=order)

                try:
                    order.send_mail(
                        email_subject, email_template, context,
                        'pretix.event.order.installment.cancelled'
                    )
                except Exception:
                    logger.exception(
                        "Failed to send cancellation email for order %s", order.code,
                    )
        except Exception:
            logger.exception(
                "Error processing expired plan %s for order %s",
                plan.pk, plan.order.code,
            )


def send_grace_period_warnings():
    """
    Sends warnings for installment plans where the grace period is about to expire.
    """
    qs = InstallmentPlan.objects.filter(
        status=InstallmentPlan.STATUS_ACTIVE,
        grace_period_end__isnull=False,
        grace_period_end__lte=now() + timedelta(hours=24),
        grace_period_end__gt=now(),
        grace_warning_sent=False
    ).select_related('order', 'order__event')

    for plan in qs:
        order = plan.order
        event = order.event

        with language(order.locale, event.settings.region):
            email_subject = event.settings.mail_subject_installment_grace_warning
            email_template = event.settings.mail_text_installment_grace_warning

            context = get_email_context(event=event, order=order)
            context.update({
                'expire_date': plan.grace_period_end,
            })

            try:
                order.send_mail(
                    email_subject, email_template, context,
                    'pretix.event.order.installment.grace_warning'
                )
                plan.grace_warning_sent = True
                plan.save(update_fields=['grace_warning_sent'])
            except Exception:
                logger.warning(
                    "Failed to send grace period warning for plan %s, order %s",
                    plan.pk, order.code,
                )


@receiver(signal=periodic_task)
@scopes_disabled()
@minimum_interval(minutes_after_success=10, minutes_after_error=2)
def run_installment_processing(sender, **kwargs):
    process_due_installments()
    process_expired_plans()
    send_grace_period_warnings()
