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
import logging
from datetime import timedelta

from django.db import models
from django.db.models import Case, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Cast, Coalesce, StrIndex, Substr
from django.dispatch import receiver
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Check, Invoice, Order, OrderFee, OrderPosition
from pretix.base.models.orders import Transaction
from pretix.base.signals import periodic_task
from pretix.celery_app import app
from pretix.helpers.periodic import minimum_interval

logger = logging.getLogger(__name__)


def check_order_transactions():
    qs = Order.objects.annotate(
        position_total=Coalesce(
            Subquery(
                OrderPosition.objects.filter(
                    order=OuterRef('pk')
                ).order_by().values('order').annotate(p=Sum('price')).values('p'),
                output_field=models.DecimalField(decimal_places=2, max_digits=10)
            ), Value(0), output_field=models.DecimalField(decimal_places=2, max_digits=10)
        ),
        fee_total=Coalesce(
            Subquery(
                OrderFee.objects.filter(
                    order=OuterRef('pk')
                ).order_by().values('order').annotate(p=Sum('value')).values('p'),
                output_field=models.DecimalField(decimal_places=2, max_digits=10)
            ), Value(0), output_field=models.DecimalField(decimal_places=2, max_digits=10)
        ),
        tx_total=Coalesce(
            Subquery(
                Transaction.objects.filter(
                    order=OuterRef('pk')
                ).order_by().values('order').annotate(p=Sum(F('price') * F('count'))).values('p'),
                output_field=models.DecimalField(decimal_places=2, max_digits=10)
            ), Value(0), output_field=models.DecimalField(decimal_places=2, max_digits=10)
        ),
    ).annotate(
        correct_total=Case(
            When(Q(status=Order.STATUS_CANCELED) | Q(status=Order.STATUS_EXPIRED) | Q(require_approval=True),
                 then=0),
            default=F('position_total') + F('fee_total'),
            output_field=models.DecimalField(decimal_places=2, max_digits=10)
        ),
    ).exclude(
        tx_total=F('correct_total')
    ).select_related('event')
    for o in qs:
        yield [
            Check.RESULT_ERROR,
            f'Order {o.full_code} has a wrong total: Status is {o.status} and sum of positions and fees is '
            f'{o.position_total + o.fee_total}, so sum of transactions should be {o.correct_total} but is {o.tx_total}'
        ]
    yield [
        Check.RESULT_OK,
        'Check completed.'
    ]


def check_order_total():
    qs = Order.objects.annotate(
        position_total=Coalesce(
            Subquery(
                OrderPosition.objects.filter(
                    order=OuterRef('pk')
                ).order_by().values('order').annotate(p=Sum('price')).values('p'),
                output_field=models.DecimalField(decimal_places=2, max_digits=10)
            ), Value(0), output_field=models.DecimalField(decimal_places=2, max_digits=10)
        ),
        fee_total=Coalesce(
            Subquery(
                OrderFee.objects.filter(
                    order=OuterRef('pk')
                ).order_by().values('order').annotate(p=Sum('value')).values('p'),
                output_field=models.DecimalField(decimal_places=2, max_digits=10)
            ), Value(0), output_field=models.DecimalField(decimal_places=2, max_digits=10)
        ),
    ).exclude(
        total=F('position_total') + F('fee_total'),
    ).select_related('event')
    for o in qs:
        if o.total != o.position_total + o.fee_total:
            yield [
                Check.RESULT_ERROR,
                f'Order {o.full_code} has a wrong total: Sum of positions and fees is '
                f'{o.position_total + o.fee_total}, but total is {o.total}'
            ]
    yield [
        Check.RESULT_OK,
        'Check completed.'
    ]


def check_invoice_gaps():
    group_qs = Invoice.objects.annotate(
        sub_prefix=Substr('invoice_no', 1, StrIndex('invoice_no', Value('-'))),
    ).order_by().values(
        'organizer', 'prefix', 'sub_prefix', 'organizer__slug'
    )
    for g in group_qs:
        numbers = Invoice.objects.filter(
            prefix=g['prefix'], organizer=g['organizer']
        )
        if g['sub_prefix']:
            numbers = numbers.filter(invoice_no__startswith=g['sub_prefix']).alias(
                real_number=Cast(Substr('invoice_no', StrIndex('invoice_no', Value('-')) + 1), models.IntegerField())
            ).order_by('real_number')
        else:
            numbers = numbers.exclude(invoice_no__contains='-').order_by('invoice_no')

        numbers = list(numbers.values_list('invoice_no', flat=True))
        previous_n = "(initial state)"
        previous_numeric_part = 0
        for n in numbers:
            numeric_part = int(n.split("-")[-1])
            if numeric_part != previous_numeric_part + 1:
                print(g)
                yield [
                    Check.RESULT_WARNING,
                    f'Organizer {g["organizer__slug"]}, prefix {g["prefix"]}, invoice {n} follows on {previous_n} with gap'
                ]
            previous_n = n
            previous_numeric_part = numeric_part

    yield [
        Check.RESULT_OK,
        'Check completed.'
    ]


@app.task()
@scopes_disabled()
def run_default_consistency_checks():
    check_functions = [
        ('pretix.orders.transactions', check_order_transactions),
        ('pretix.orders.total', check_order_total),
        ('pretix.invoices.gaps', check_invoice_gaps),
    ]
    for check_type, check_function in check_functions:
        r = Check.RESULT_OK
        log = []
        try:
            for result, logline in check_function():
                if result == Check.RESULT_WARNING and r == Check.RESULT_OK:
                    r = Check.RESULT_WARNING
                elif result == Check.RESULT_ERROR:
                    r = Check.RESULT_ERROR
                log.append(f'[{result}] {logline}')
        except Exception as e:
            logger.exception('Could not run consistency check')
            r = Check.RESULT_ERROR
            log.append(f'[error] Check aborted: {e}')

        Check.objects.create(result=r, check_type=check_type, log='\n'.join(log))

    Check.objects.filter(created__lt=now() - timedelta(days=90)).delete()


@receiver(signal=periodic_task)
@minimum_interval(minutes_after_success=24 * 60)
def periodic_consistency_checks(sender, **kwargs):
    run_default_consistency_checks.apply_async()
