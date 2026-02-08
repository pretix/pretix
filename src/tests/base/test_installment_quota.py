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
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, InstallmentPlan, Item, Order, OrderPayment, OrderPosition,
    Organizer, Quota,
)


@pytest.fixture
def env():
    with scopes_disabled():
        orga = Organizer.objects.create(name='TestOrg', slug='testorg')
        event = Event.objects.create(
            organizer=orga, name='TestEvent', slug='testevent',
            date_from=now(), live=True,
        )
        item = Item.objects.create(event=event, name='Ticket', default_price=Decimal('300.00'))
        quota = Quota.objects.create(event=event, name='Quota', size=10)
        quota.items.add(item)
        yield orga, event, item, quota


def _create_order_with_position(orga, event, item, code, status=Order.STATUS_PENDING):
    order = Order.objects.create(
        code=code, event=event, email='test@localhost',
        status=status, datetime=now(), expires=now() + timedelta(days=10),
        total=Decimal('300.00'), locale='en',
        sales_channel=orga.sales_channels.get(identifier="web"),
    )
    OrderPosition.objects.create(order=order, item=item, price=Decimal('300.00'), positionid=1)
    return order


@pytest.mark.django_db
class TestInstallmentQuotaLocking:

    def test_quota_held_during_active_plan(self, env):
        orga, event, item, quota = env
        with scopes_disabled():
            order = _create_order_with_position(orga, event, item, 'TEST1', Order.STATUS_PAID)
            InstallmentPlan.objects.create(
                order=order, payment_provider='dummy', payment_token={'token': 'test'},
                total_installments=3, installments_paid=1,
                amount_per_installment=Decimal('100.00'), status=InstallmentPlan.STATUS_ACTIVE,
            )
            assert item.check_quotas() == (Quota.AVAILABILITY_OK, 9)

    def test_quota_released_on_cancellation(self, env):
        orga, event, item, quota = env
        with scopes_disabled():
            order = _create_order_with_position(orga, event, item, 'TEST2', Order.STATUS_PAID)
            InstallmentPlan.objects.create(
                order=order, payment_provider='dummy', payment_token={'token': 'test'},
                total_installments=3, installments_paid=1,
                amount_per_installment=Decimal('100.00'), status=InstallmentPlan.STATUS_ACTIVE,
            )
            assert item.check_quotas() == (Quota.AVAILABILITY_OK, 9)

            order.status = Order.STATUS_CANCELED
            order.save()
            assert item.check_quotas() == (Quota.AVAILABILITY_OK, 10)

    def test_no_double_decrement_on_subsequent_payments(self, env):
        orga, event, item, quota = env
        with scopes_disabled():
            order = _create_order_with_position(orga, event, item, 'TEST3', Order.STATUS_PAID)
            plan = InstallmentPlan.objects.create(
                order=order, payment_provider='dummy', payment_token={'token': 'test'},
                total_installments=3, installments_paid=1,
                amount_per_installment=Decimal('100.00'), status=InstallmentPlan.STATUS_ACTIVE,
            )
            for _ in range(3):
                OrderPayment.objects.create(
                    order=order, state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                    amount=Decimal('100.00'), payment_date=now(),
                    provider='dummy', installment_plan=plan,
                )

            plan.installments_paid = 3
            plan.status = InstallmentPlan.STATUS_COMPLETED
            plan.save()
            assert item.check_quotas() == (Quota.AVAILABILITY_OK, 9)
