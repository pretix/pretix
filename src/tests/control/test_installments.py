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
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import Event, Order, Organizer
from pretix.base.models.orders import InstallmentPlan, ScheduledInstallment


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    with scope(organizer=o):
        event = Event.objects.create(
            organizer=o, name='Dummy Event', slug='dummy', date_from=now(),
        )
        yield event


@pytest.fixture
def orders(event):
    with scope(organizer=event.organizer):
        order_no_plan = Order.objects.create(
            code='NOPLAN', event=event, email='test1@example.com',
            status=Order.STATUS_PAID, datetime=now(),
            expires=now() + timedelta(days=10), total=Decimal('100.00'),
            locale='en',
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
        )
        order_active = Order.objects.create(
            code='ACTIVE', event=event, email='test2@example.com',
            status=Order.STATUS_PENDING, datetime=now(),
            expires=now() + timedelta(days=10), total=Decimal('300.00'),
            locale='en',
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
        )
        InstallmentPlan.objects.create(
            order=order_active, payment_provider='dummy',
            payment_token={'token': 'tok_active'}, total_installments=3,
            installments_paid=1, amount_per_installment=Decimal('100.00'),
            status=InstallmentPlan.STATUS_ACTIVE,
        )
        order_completed = Order.objects.create(
            code='COMPLETED', event=event, email='test3@example.com',
            status=Order.STATUS_PAID, datetime=now(),
            expires=now() + timedelta(days=10), total=Decimal('300.00'),
            locale='en',
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
        )
        InstallmentPlan.objects.create(
            order=order_completed, payment_provider='dummy',
            payment_token={}, total_installments=3,
            installments_paid=3, amount_per_installment=Decimal('100.00'),
            status=InstallmentPlan.STATUS_COMPLETED,
        )
        order_failed = Order.objects.create(
            code='FAILED', event=event, email='test4@example.com',
            status=Order.STATUS_PENDING, datetime=now(),
            expires=now() + timedelta(days=10), total=Decimal('300.00'),
            locale='en',
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
        )
        plan_failed = InstallmentPlan.objects.create(
            order=order_failed, payment_provider='dummy',
            payment_token={'token': 'tok_failed'}, total_installments=3,
            installments_paid=1, amount_per_installment=Decimal('100.00'),
            status=InstallmentPlan.STATUS_ACTIVE,
            grace_period_end=now() + timedelta(days=5),
        )
        ScheduledInstallment.objects.create(
            plan=plan_failed, installment_number=2, amount=Decimal('100.00'),
            due_date=now() - timedelta(days=2), state=ScheduledInstallment.STATE_FAILED,
        )

        yield {
            'no_plan': order_no_plan,
            'active': order_active,
            'completed': order_completed,
            'failed': order_failed,
        }


@pytest.mark.django_db
class TestInstallmentFilters:

    def test_filter_no_plan(self, orders):
        with scope(organizer=orders['no_plan'].event.organizer):
            qs = Order.objects.filter(installment_plan__isnull=True)
            assert orders['no_plan'] in qs
            assert orders['active'] not in qs

    def test_filter_active(self, orders):
        with scope(organizer=orders['active'].event.organizer):
            qs = Order.objects.filter(
                installment_plan__status=InstallmentPlan.STATUS_ACTIVE,
                installment_plan__grace_period_end__isnull=True,
            )
            assert orders['active'] in qs
            assert orders['no_plan'] not in qs
            assert orders['completed'] not in qs
            assert orders['failed'] not in qs

    def test_filter_completed(self, orders):
        with scope(organizer=orders['completed'].event.organizer):
            qs = Order.objects.filter(
                installment_plan__status=InstallmentPlan.STATUS_COMPLETED,
            )
            assert orders['completed'] in qs
            assert orders['active'] not in qs

    def test_filter_grace_period(self, orders):
        with scope(organizer=orders['failed'].event.organizer):
            qs = Order.objects.filter(
                installment_plan__grace_period_end__isnull=False,
            )
            assert orders['failed'] in qs
            assert orders['active'] not in qs
            assert orders['completed'] not in qs
