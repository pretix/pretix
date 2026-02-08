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
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import (
    CartPosition, Event, Item, Order, OrderPayment, Organizer, Quota,
)
from pretix.base.models.orders import InstallmentPlan, ScheduledInstallment
from pretix.base.services.installments import create_installment_plan
from pretix.base.services.orders import perform_order


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    with scope(organizer=o):
        event = Event.objects.create(
            organizer=o,
            name='Dummy Event',
            slug='dummy',
            date_from=now(),
            plugins='tests.testdummy',
        )
        yield event


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
def item(event):
    return Item.objects.create(event=event, name="Ticket", default_price=Decimal('100.00'))


@pytest.fixture
def quota(event, item):
    q = Quota.objects.create(event=event, name="Quota", size=None)
    q.items.add(item)
    return q


@pytest.fixture
def cart_position(event, item, quota):
    return CartPosition.objects.create(
        event=event,
        item=item,
        price=Decimal('100.00'),
        expires=now() + timedelta(days=1),
    )


def _mock_provider(max_installments=10):
    p = MagicMock()
    p.installments_supported = True
    p.get_max_installments_for_cart.return_value = max_installments
    return p


def _mock_order_provider(default_count=3, max_installments=10):
    p = MagicMock()
    p.installments_supported = True
    p.calculate_fee.return_value = Decimal('0.00')
    p.payment_form_fields = {}
    p.is_implicit = lambda x: False
    p.installments_available.return_value = True
    p.settings.get.return_value = default_count
    p.get_max_installments_for_cart.return_value = max_installments
    return p


@pytest.mark.django_db
class TestCreateInstallmentPlan:

    def test_happy_path(self, event, order):
        with scope(organizer=event.organizer):
            with patch.object(event, 'get_payment_providers', return_value={'dummy': _mock_provider()}):
                plan = create_installment_plan(order, 'dummy', installments_count=3)

            assert plan.total_installments == 3
            assert plan.status == InstallmentPlan.STATUS_ACTIVE
            assert plan.amount_per_installment == Decimal('100.00')
            assert plan.payment_token == {}

            installments = list(plan.installments.order_by('installment_number'))
            assert len(installments) == 3
            assert installments[0].installment_number == 1
            assert installments[0].amount == Decimal('100.00')
            assert installments[0].payment == order.payments.first()
            assert installments[1].installment_number == 2
            assert installments[1].amount == Decimal('100.00')
            assert installments[1].state == ScheduledInstallment.STATE_PENDING

            first_payment = order.payments.first()
            assert first_payment.amount == Decimal('100.00')
            assert first_payment.installment_plan == plan

    def test_rounding(self, event, order):
        order.total = Decimal('100.00')
        order.save()

        with scope(organizer=event.organizer):
            with patch.object(event, 'get_payment_providers', return_value={'dummy': _mock_provider()}):
                plan = create_installment_plan(order, 'dummy', installments_count=3)

            assert plan.amount_per_installment == Decimal('33.33')

            installments = list(plan.installments.order_by('installment_number'))
            assert len(installments) == 3
            assert installments[0].amount == Decimal('33.33')
            assert installments[2].amount == Decimal('33.34')

            first_payment = OrderPayment.objects.get(order=order)
            assert first_payment.amount == Decimal('33.33')

    def test_unsupported_provider_raises(self, event, order):
        with scope(organizer=event.organizer):
            with pytest.raises(ValueError, match="does not support installments"):
                create_installment_plan(order, 'banktransfer', installments_count=3)

    def test_exceeds_max_installments_raises(self, event, order):
        with scope(organizer=event.organizer):
            with patch.object(event, 'get_payment_providers', return_value={'dummy': _mock_provider(max_installments=1)}):
                with pytest.raises(ValueError, match="exceeds the maximum"):
                    create_installment_plan(order, 'dummy', installments_count=3)

    def test_calendar_month_due_dates(self, event, order):
        from freezegun import freeze_time

        with freeze_time("2025-01-31 12:00:00"):
            with scope(organizer=event.organizer):
                with patch.object(event, 'get_payment_providers', return_value={'dummy': _mock_provider()}):
                    plan = create_installment_plan(order, 'dummy', installments_count=4)

                installments = list(plan.installments.order_by('installment_number'))
                assert installments[0].due_date.month == 1
                assert installments[0].due_date.day == 31
                assert installments[1].due_date.month == 2
                assert installments[1].due_date.day == 28
                assert installments[2].due_date.month == 3
                assert installments[2].due_date.day == 31
                assert installments[3].due_date.month == 4
                assert installments[3].due_date.day == 30

    def test_info_data_preserved(self, order):
        with scope(organizer=order.event.organizer):
            with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': _mock_provider()}):
                plan = create_installment_plan(
                    order, 'dummy', installments_count=3,
                    info_data={'card_last4': '4242', 'transaction_id': 'txn_123'},
                )

            payment = plan.order.payments.first()
            assert payment.info == '{"card_last4": "4242", "transaction_id": "txn_123"}'
            assert payment.state == OrderPayment.PAYMENT_STATE_CREATED


@pytest.mark.django_db
class TestPerformOrderWithInstallments:

    def _perform(self, event, cart_position, provider, installments_count=None):
        payment_request = {
            'provider': 'dummy',
            'payment_amount': Decimal('100.00'),
            'info_data': {},
            'pay_in_installments': True,
        }
        if installments_count is not None:
            payment_request['installments_count'] = installments_count

        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': provider}):
            return perform_order(
                event=event.id,
                payments=[payment_request],
                positions=[cart_position.id],
                meta_info={},
                email='test@example.com',
                locale='en',
            )

    def test_creates_plan(self, event, cart_position):
        with scope(organizer=event.organizer):
            result = self._perform(event, cart_position, _mock_order_provider())
            order = Order.objects.get(pk=result['order_id'])

            assert order.installment_plan is not None
            assert order.installment_plan.total_installments == 3
            assert order.payments.first().amount == Decimal('33.33')

    def test_uses_user_selected_count(self, event, cart_position):
        with scope(organizer=event.organizer):
            result = self._perform(event, cart_position, _mock_order_provider(), installments_count=5)
            order = Order.objects.get(pk=result['order_id'])

            assert order.installment_plan.total_installments == 5
            assert order.payments.first().amount == Decimal('20.00')

    def test_caps_at_provider_max(self, event, cart_position):
        with scope(organizer=event.organizer):
            result = self._perform(
                event, cart_position,
                _mock_order_provider(max_installments=4),
                installments_count=10,
            )
            order = Order.objects.get(pk=result['order_id'])

            assert order.installment_plan.total_installments == 4
            assert order.payments.first().amount == Decimal('25.00')

    def test_with_multi_use_payment(self, event, cart_position):
        provider = _mock_order_provider()
        gc_provider = MagicMock()
        gc_provider.calculate_fee.return_value = Decimal('0.00')
        gc_provider.payment_form_fields = {}
        gc_provider.is_implicit = lambda x: False

        gift_card_payment = {
            'provider': 'multiuse',
            'payment_amount': Decimal('0.00'),
            'max_value': '40.00',
            'info_data': {},
            'multi_use_supported': True,
        }
        installment_payment = {
            'provider': 'dummy',
            'payment_amount': Decimal('0.00'),
            'info_data': {},
            'pay_in_installments': True,
            'installments_count': 3,
        }
        providers = {'dummy': provider, 'multiuse': gc_provider}
        with scope(organizer=event.organizer):
            with patch('pretix.base.models.Event.get_payment_providers', return_value=providers):
                result = perform_order(
                    event=event.id,
                    payments=[gift_card_payment, installment_payment],
                    positions=[cart_position.id],
                    meta_info={},
                    email='test@example.com',
                    locale='en',
                )
            order = Order.objects.get(pk=result['order_id'])

            assert order.payments.count() == 2
            gc_payment = order.payments.get(provider='multiuse')
            assert gc_payment.amount == Decimal('40.00')

            assert order.installment_plan is not None
            assert order.installment_plan.total_installments == 3
            assert order.installment_plan.amount_per_installment == Decimal('20.00')
            first_installment_payment = order.payments.filter(installment_plan=order.installment_plan).first()
            assert first_installment_payment.amount == Decimal('20.00')
