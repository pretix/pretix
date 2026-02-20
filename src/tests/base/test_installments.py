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
from django.db import IntegrityError, transaction
from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.testdummy.payment import DummyPaymentProvider

from pretix.base.models import Event, Order, OrderPayment, Organizer
from pretix.base.models.orders import InstallmentPlan, ScheduledInstallment


@pytest.fixture
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
def event(organizer):
    return Event.objects.create(
        organizer=organizer,
        name='Dummy Event',
        slug='dummy',
        date_from=now(),
    )


@pytest.fixture
def order(event):
    return Order.objects.create(
        code='ABCDE',
        event=event,
        email='test@example.com',
        status=Order.STATUS_PENDING,
        datetime=now(),
        expires=now() + timedelta(days=10),
        total=Decimal('300.00'),
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
    )


@pytest.fixture
def plan(order):
    return InstallmentPlan.objects.create(
        order=order,
        payment_provider='dummy',
        payment_token={'token': 'tok_123'},
        total_installments=3,
        installments_paid=0,
        amount_per_installment=Decimal('100.00'),
        status=InstallmentPlan.STATUS_ACTIVE,
    )


@pytest.mark.django_db
class TestInstallmentPlanModel:

    def test_order_unique_constraint(self, order):
        InstallmentPlan.objects.create(
            order=order,
            payment_provider='stripe',
            payment_token={},
            total_installments=3,
            installments_paid=0,
            amount_per_installment=Decimal('100.00'),
            status=InstallmentPlan.STATUS_ACTIVE,
        )
        with pytest.raises(IntegrityError):
            InstallmentPlan.objects.create(
                order=order,
                payment_provider='paypal',
                payment_token={},
                total_installments=2,
                installments_paid=0,
                amount_per_installment=Decimal('150.00'),
                status=InstallmentPlan.STATUS_ACTIVE,
            )

    def test_store_payment_token(self, plan):
        plan.store_payment_token({'token': 'test', 'customer_id': 'cus_123'})
        plan.refresh_from_db()
        assert plan.payment_token == {'token': 'test', 'customer_id': 'cus_123'}

    @pytest.mark.parametrize("invalid_token", [None, {}])
    def test_store_payment_token_rejects_empty(self, plan, invalid_token):
        with pytest.raises(ValueError, match="cannot be None or empty"):
            plan.store_payment_token(invalid_token)

    def test_str(self, plan):
        assert plan.order.code in str(plan)

    def test_record_successful_payment(self, plan):
        plan.grace_period_end = now()
        plan.grace_warning_sent = True
        plan.save()

        completed = plan.record_successful_payment()

        plan.refresh_from_db()
        assert plan.installments_paid == 1
        assert plan.grace_period_end is None
        assert plan.grace_warning_sent is False
        assert not completed

    def test_record_successful_payment_completes(self, plan):
        plan.installments_paid = 2
        plan.total_installments = 3
        plan.save()

        completed = plan.record_successful_payment()

        plan.refresh_from_db()
        assert plan.installments_paid == 3
        assert plan.status == InstallmentPlan.STATUS_COMPLETED
        assert completed


@pytest.mark.django_db
class TestScheduledInstallmentModel:

    @scopes_disabled()
    def test_ordering_by_installment_number(self, plan):
        for num in [3, 1, 2]:
            ScheduledInstallment.objects.create(
                plan=plan,
                installment_number=num,
                amount=Decimal('100.00'),
                due_date=now() + timedelta(days=30 * num),
                state=ScheduledInstallment.STATE_PENDING,
            )

        numbers = list(plan.installments.values_list('installment_number', flat=True))
        assert numbers == [1, 2, 3]

    @scopes_disabled()
    def test_unique_together_plan_and_number(self, plan):
        ScheduledInstallment.objects.create(
            plan=plan, installment_number=1, amount=Decimal('100.00'),
            due_date=now() + timedelta(days=30), state=ScheduledInstallment.STATE_PENDING,
        )
        with pytest.raises(IntegrityError):
            ScheduledInstallment.objects.create(
                plan=plan, installment_number=1, amount=Decimal('100.00'),
                due_date=now() + timedelta(days=60), state=ScheduledInstallment.STATE_PENDING,
            )


@pytest.mark.django_db
class TestForeignKeyConstraints:

    @scopes_disabled()
    def test_order_deletion_protected(self, plan):
        with pytest.raises(Exception):
            with transaction.atomic():
                plan.order.delete()
        assert InstallmentPlan.objects.filter(pk=plan.pk).exists()

    @scopes_disabled()
    def test_plan_deletion_cascades_to_installments(self, plan):
        inst = ScheduledInstallment.objects.create(
            plan=plan,
            installment_number=2,
            amount=Decimal('100.00'),
            due_date=now() + timedelta(days=30),
            state=ScheduledInstallment.STATE_PENDING,
        )
        plan.delete()
        assert not ScheduledInstallment.objects.filter(pk=inst.pk).exists()

    @scopes_disabled()
    def test_payment_deletion_nullifies_installment_reference(self, plan):
        payment = OrderPayment.objects.create(
            order=plan.order,
            provider='stripe',
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            amount=Decimal('100.00'),
        )
        inst = ScheduledInstallment.objects.create(
            plan=plan,
            installment_number=2,
            amount=Decimal('100.00'),
            due_date=now() + timedelta(days=30),
            state=ScheduledInstallment.STATE_PAID,
            payment=payment,
        )
        payment.delete()
        inst.refresh_from_db()
        assert inst.payment is None


@pytest.mark.django_db
class TestPaymentProviderInstallmentInterface:

    def test_installments_supported_defaults_to_false(self, event):
        assert DummyPaymentProvider(event).installments_supported is False

    def test_execute_installment_raises_not_implemented(self, event, plan):
        inst = ScheduledInstallment.objects.create(
            plan=plan,
            installment_number=2,
            amount=Decimal('100.00'),
            due_date=now() + timedelta(days=30),
            state=ScheduledInstallment.STATE_PENDING,
        )
        with pytest.raises(NotImplementedError):
            DummyPaymentProvider(event).execute_installment(plan, inst)

    def test_revoke_payment_token_raises_not_implemented(self, event, plan):
        with pytest.raises(NotImplementedError):
            DummyPaymentProvider(event).revoke_payment_token(plan)
