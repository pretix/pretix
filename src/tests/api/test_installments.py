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

from pretix.base.models import Event, Item, Order, OrderPosition, Organizer
from pretix.base.models.orders import InstallmentPlan, ScheduledInstallment


@pytest.fixture
def env(client):
    orga = Organizer.objects.create(name='CCC', slug='ccc')
    with scope(organizer=orga):
        event = Event.objects.create(
            organizer=orga, name='30C3', slug='30c3',
            date_from=now(), live=True,
        )
        item = Item.objects.create(event=event, name='Ticket', default_price=Decimal('100.00'))
        order = Order.objects.create(
            code='ABC12', event=event, email='admin@localhost',
            status=Order.STATUS_PENDING, datetime=now(),
            expires=now() + timedelta(days=10), total=Decimal('300.00'),
            locale='en',
            sales_channel=orga.sales_channels.get(identifier="web"),
        )
        OrderPosition.objects.create(order=order, item=item, price=Decimal('300.00'), positionid=1)
        plan = InstallmentPlan.objects.create(
            order=order, payment_provider='dummy',
            payment_token={'token': 'tok_test'}, total_installments=3,
            installments_paid=1, amount_per_installment=Decimal('100.00'),
            status=InstallmentPlan.STATUS_ACTIVE,
        )
        ScheduledInstallment.objects.create(
            plan=plan, installment_number=2, amount=Decimal('100.00'),
            due_date=now() + timedelta(days=30), state=ScheduledInstallment.STATE_PENDING,
        )
        ScheduledInstallment.objects.create(
            plan=plan, installment_number=3, amount=Decimal('100.00'),
            due_date=now() + timedelta(days=60), state=ScheduledInstallment.STATE_PENDING,
        )
        yield orga, event, order, plan


@pytest.fixture
def token_client(client, env):
    orga, event, order, plan = env
    t = orga.teams.create(name='Test team', can_view_orders=True, can_change_orders=True)
    t.members.create(email='admin@localhost')
    t.limit_events.add(event)
    token = t.tokens.create(name='Test token')
    client.credentials(HTTP_AUTHORIZATION='Token ' + token.token)
    return client


def _url(orga, event, order, suffix=''):
    return f'/api/v1/organizers/{orga.slug}/events/{event.slug}/orders/{order.code}/installment-plan/{suffix}'


def _order_without_plan(orga, event, code='NOPLAN'):
    return Order.objects.create(
        code=code, event=event, email='test@localhost',
        status=Order.STATUS_PENDING, datetime=now(),
        expires=now() + timedelta(days=10), total=Decimal('100.00'),
        locale='en',
        sales_channel=orga.sales_channels.get(identifier="web"),
    )


@pytest.mark.django_db
class TestInstallmentPlanAPI:

    def test_get_plan(self, token_client, env):
        orga, event, order, plan = env
        resp = token_client.get(_url(orga, event, order))
        assert resp.status_code == 200
        assert resp.data['status'] == 'active'
        assert resp.data['total_installments'] == 3
        assert resp.data['installments_paid'] == 1
        assert resp.data['amount_per_installment'] == '100.00'

    def test_get_plan_404_without_plan(self, token_client, env):
        orga, event, order, plan = env
        with scope(organizer=orga):
            order2 = _order_without_plan(orga, event, 'DEF45')
        resp = token_client.get(_url(orga, event, order2))
        assert resp.status_code == 404

    def test_get_requires_authentication(self, client, env):
        orga, event, order, plan = env
        resp = client.get(_url(orga, event, order))
        assert resp.status_code == 401

    def test_list_installments(self, token_client, env):
        orga, event, order, plan = env
        resp = token_client.get(_url(orga, event, order, 'installments/'))
        assert resp.status_code == 200
        assert len(resp.data['results']) == 2
        assert resp.data['results'][0]['installment_number'] == 2
        assert resp.data['results'][0]['amount'] == '100.00'
        assert resp.data['results'][0]['state'] == 'pending'

    def test_list_installments_404_without_plan(self, token_client, env):
        orga, event, order, plan = env
        with scope(organizer=orga):
            order2 = _order_without_plan(orga, event, 'XYZ99')
        resp = token_client.get(_url(orga, event, order2, 'installments/'))
        assert resp.status_code == 404

    def test_retry_installment(self, token_client, env, mocker):
        orga, event, order, plan = env
        with scope(organizer=orga):
            installment = plan.installments.first()
            installment.state = ScheduledInstallment.STATE_FAILED
            installment.save()

        mocker.patch('pretix.api.views.order.process_single_installment', return_value=True)
        resp = token_client.post(_url(orga, event, order, 'retry/'))
        assert resp.status_code == 200

    def test_retry_installment_no_failed(self, token_client, env):
        orga, event, order, plan = env
        resp = token_client.post(_url(orga, event, order, 'retry/'))
        assert resp.status_code == 400

    def test_cancel_plan(self, token_client, env):
        orga, event, order, plan = env
        resp = token_client.delete(_url(orga, event, order))
        assert resp.status_code == 204

        plan.refresh_from_db()
        assert plan.status == InstallmentPlan.STATUS_CANCELLED
        with scope(organizer=orga):
            assert plan.installments.filter(state=ScheduledInstallment.STATE_PENDING).count() == 0

    def test_cancel_plan_and_order(self, token_client, env):
        orga, event, order, plan = env
        resp = token_client.delete(_url(orga, event, order) + '?cancel_order=true')
        assert resp.status_code == 204

        plan.refresh_from_db()
        order.refresh_from_db()
        assert plan.status == InstallmentPlan.STATUS_CANCELLED
        assert order.status == Order.STATUS_CANCELED

    def test_cancel_plan_404_without_plan(self, token_client, env):
        orga, event, order, plan = env
        with scope(organizer=orga):
            order2 = _order_without_plan(orga, event, 'LMN88')
        resp = token_client.delete(_url(orga, event, order2))
        assert resp.status_code == 404
