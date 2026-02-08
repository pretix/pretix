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
from unittest.mock import MagicMock, patch

import pytest
from django.core import mail
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import (
    Event, Item, Order, OrderPayment, OrderPosition, Organizer,
)
from pretix.base.models.orders import InstallmentPlan, ScheduledInstallment
from pretix.base.services.installments import (
    process_due_installments, process_expired_plans
)


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    with scope(organizer=o):
        event = Event.objects.create(
            organizer=o,
            name='Dummy Event',
            slug='dummy',
            date_from=now(),
        )
        yield event


@pytest.fixture
def order(event):
    order = Order.objects.create(
        code='ABCDE',
        event=event,
        email='test@example.com',
        status=Order.STATUS_PENDING,
        datetime=now(),
        expires=now() + timedelta(days=10),
        total=Decimal('300.00'),
        locale='en',
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
    )
    item = Item.objects.create(event=event, name='Test Ticket', default_price=Decimal('300.00'))
    OrderPosition.objects.create(order=order, item=item, price=Decimal('300.00'), positionid=1)
    return order


@pytest.fixture
def plan(order):
    return InstallmentPlan.objects.create(
        order=order,
        payment_provider='dummy',
        payment_token={'token': 'tok_123'},
        total_installments=3,
        installments_paid=1,
        amount_per_installment=Decimal('100.00'),
        status=InstallmentPlan.STATUS_ACTIVE,
    )


def _mock_provider(execute_result=True, grace_period_days=7, reminder_days=3):
    p = MagicMock()
    p.installments_supported = True
    p.execute_installment.return_value = execute_result
    p.settings.get.return_value = grace_period_days
    return p


def _patch_providers(provider):
    return patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': provider})


@pytest.mark.django_db
class TestProcessDueInstallments:

    def test_success(self, event, order, plan):
        inst = ScheduledInstallment.objects.create(
            plan=plan, installment_number=2, amount=Decimal('100.00'),
            due_date=now() - timedelta(days=1), state=ScheduledInstallment.STATE_PENDING,
        )

        with _patch_providers(_mock_provider()):
            with scope(organizer=event.organizer):
                process_due_installments()

        inst.refresh_from_db()
        plan.refresh_from_db()
        assert inst.state == ScheduledInstallment.STATE_PAID
        assert inst.payment is not None
        assert inst.payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED
        assert plan.installments_paid == 2

    def test_ignores_future(self, event, order, plan):
        inst = ScheduledInstallment.objects.create(
            plan=plan, installment_number=2, amount=Decimal('100.00'),
            due_date=now() + timedelta(days=1), state=ScheduledInstallment.STATE_PENDING,
        )

        with _patch_providers(_mock_provider()):
            with scope(organizer=event.organizer):
                process_due_installments()

        inst.refresh_from_db()
        assert inst.state == ScheduledInstallment.STATE_PENDING

    def test_skips_already_paid(self, event, order, plan):
        ScheduledInstallment.objects.create(
            plan=plan, installment_number=2, amount=Decimal('100.00'),
            due_date=now() - timedelta(days=1), state=ScheduledInstallment.STATE_PAID,
        )
        provider = _mock_provider()

        with _patch_providers(provider):
            with scope(organizer=event.organizer):
                process_due_installments()

        assert not provider.execute_installment.called

    def test_failure_sets_grace_period(self, event, order, plan):
        inst = ScheduledInstallment.objects.create(
            plan=plan, installment_number=2, amount=Decimal('100.00'),
            due_date=now() - timedelta(days=1), state=ScheduledInstallment.STATE_PENDING,
        )

        with _patch_providers(_mock_provider(execute_result=False)):
            with scope(organizer=event.organizer):
                process_due_installments()

        inst.refresh_from_db()
        plan.refresh_from_db()
        assert inst.state == ScheduledInstallment.STATE_FAILED
        assert plan.grace_period_end is not None

    def test_completes_plan_on_final_installment(self, event, order, plan):
        plan.total_installments = 2
        plan.save()

        ScheduledInstallment.objects.create(
            plan=plan, installment_number=2, amount=Decimal('100.00'),
            due_date=now() - timedelta(days=1), state=ScheduledInstallment.STATE_PENDING,
        )
        provider = _mock_provider()

        with _patch_providers(provider):
            with scope(organizer=event.organizer):
                process_due_installments()

        plan.refresh_from_db()
        assert plan.status == InstallmentPlan.STATUS_COMPLETED
        assert plan.installments_paid == 2
        provider.revoke_payment_token.assert_called_with(plan)


@pytest.mark.django_db
class TestProcessExpiredPlans:

    def test_cancels_order_and_plan(self, event, order, plan):
        plan.grace_period_end = now() - timedelta(days=1)
        plan.save()
        inst = ScheduledInstallment.objects.create(
            plan=plan, installment_number=2, amount=Decimal('100.00'),
            due_date=now() - timedelta(days=5), state=ScheduledInstallment.STATE_PENDING,
        )
        provider = _mock_provider()

        with _patch_providers(provider):
            with scope(organizer=event.organizer):
                process_expired_plans()

        order.refresh_from_db()
        plan.refresh_from_db()
        inst.refresh_from_db()
        assert order.status == Order.STATUS_CANCELED
        assert plan.status == InstallmentPlan.STATUS_CANCELLED
        assert inst.state == ScheduledInstallment.STATE_CANCELLED
        provider.revoke_payment_token.assert_called_with(plan)

    def test_sends_cancellation_email(self, event, order, plan):
        plan.grace_period_end = now() - timedelta(days=1)
        plan.save()
        mail.outbox = []

        with _patch_providers(_mock_provider()):
            with scope(organizer=event.organizer):
                process_expired_plans()

        assert len(mail.outbox) == 1
        assert order.code in mail.outbox[0].subject
