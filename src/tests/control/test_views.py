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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze, oocf
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import datetime
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import (
    Event, Item, ItemCategory, Order, OrderPosition, Organizer, Question,
    Quota, Team, User, Voucher,
)


@pytest.fixture
def event():
    orga = Organizer.objects.create(name='CCC', slug='ccc')
    return Event.objects.create(
        organizer=orga, name='30C3', slug='30c3',
        date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        plugins='pretix.plugins.banktransfer,tests.testdummy',
    )


@pytest.fixture
def item(event):
    return Item.objects.create(name='Test item', event=event, default_price=13)


@pytest.fixture
def item_category(event):
    return ItemCategory.objects.create(event=event)


@pytest.fixture
def order(item):
    o = Order.objects.create(event=item.event, status=Order.STATUS_PENDING,
                             expires=now() + datetime.timedelta(hours=1),
                             total=13, code='DUMMY', email='dummy@dummy.test',
                             sales_channel=item.event.organizer.sales_channels.get(identifier="web"),
                             datetime=now())
    OrderPosition.objects.create(order=o, item=item, price=13)
    p1 = o.payments.create(
        provider='stripe',
        state='refunded',
        amount=Decimal('23.00'),
        payment_date=o.datetime,
    )
    o.refunds.create(
        provider='stripe',
        state='done',
        source='admin',
        amount=Decimal('23.00'),
        execution_date=o.datetime,
        payment=p1,
    )
    return o


@pytest.fixture
def question(event):
    return Question.objects.create(event=event, question="What is your shoe size?", type="N", required=True)


@pytest.fixture
def quota(event):
    return Quota.objects.create(name="Test", size=2, event=event)


@pytest.fixture
def voucher(quota):
    return Voucher.objects.create(event=quota.event, quota=quota)


@pytest.fixture
def logged_in_client(client, event):
    user = User.objects.create_superuser('dummy@dummy.dummy', 'dummy')
    t = Team.objects.create(
        organizer=event.organizer,
        all_events=True, can_create_events=True, can_change_teams=True,
        can_change_organizer_settings=True, can_change_event_settings=True, can_change_items=True,
        can_view_orders=True, can_change_orders=True, can_view_vouchers=True, can_change_vouchers=True
    )
    t.members.add(user)
    client.force_login(user)
    user.staffsession_set.create(date_start=now(), session_key=client.session.session_key)
    return client


@pytest.mark.parametrize('url,expected', [
    ('/control/', 200),
    ('/control/settings/2fa/', 302),
    ('/control/settings/history/', 200),
    ('/control/settings/oauth/authorized/', 200),
    ('/control/settings/oauth/apps/', 200),
    ('/control/settings/oauth/apps/add', 200),

    ('/control/global/settings/', 200),
    ('/control/global/update/', 200),

    ('/control/organizers/', 200),
    ('/control/organizers/add', 200),
    ('/control/organizer/{orga}/edit', 200),
    ('/control/organizer/{orga}/teams', 200),
    ('/control/organizer/{orga}/devices', 200),
    ('/control/organizer/{orga}/webhooks', 200),
    ('/control/organizer/{orga}/giftcards', 200),

    ('/control/events/', 200),
    ('/control/events/add', 200),

    ('/control/event/{orga}/{event}/', 200),
    ('/control/event/{orga}/{event}/qrcode.png', 200),
    ('/control/event/{orga}/{event}/qrcode.jpeg', 200),
    ('/control/event/{orga}/{event}/qrcode.svg', 200),
    ('/control/event/{orga}/{event}/qrcode.gif', 200),
    ('/control/event/{orga}/{event}/live/', 200),
    ('/control/event/{orga}/{event}/dangerzone/', 200),
    ('/control/event/{orga}/{event}/cancel/', 200),
    ('/control/event/{orga}/{event}/settings/', 200),
    ('/control/event/{orga}/{event}/settings/plugins', 200),
    ('/control/event/{orga}/{event}/settings/payment', 200),
    ('/control/event/{orga}/{event}/settings/tickets', 200),
    ('/control/event/{orga}/{event}/settings/widget', 200),
    # ('/control/event/{orga}/{event}/settings/tickets/preview/(?P<output>[^/]+)', 200),
    ('/control/event/{orga}/{event}/settings/email', 200),
    ('/control/event/{orga}/{event}/settings/cancel', 200),
    ('/control/event/{orga}/{event}/settings/invoice', 200),
    ('/control/event/{orga}/{event}/settings/invoice/preview', 200),
    ('/control/event/{orga}/{event}/items/', 200),
    ('/control/event/{orga}/{event}/items/add', 200),
    ('/control/event/{orga}/{event}/items/{item}/', 200),
    ('/control/event/{orga}/{event}/items/{item}/delete', 200),
    ('/control/event/{orga}/{event}/categories/', 200),
    ('/control/event/{orga}/{event}/categories/{category}/delete', 200),
    ('/control/event/{orga}/{event}/categories/{category}/', 200),
    ('/control/event/{orga}/{event}/categories/add', 200),
    ('/control/event/{orga}/{event}/questions/', 200),
    ('/control/event/{orga}/{event}/questions/{question}/delete', 200),
    ('/control/event/{orga}/{event}/questions/{question}/', 200),
    ('/control/event/{orga}/{event}/questions/{question}/change', 200),
    ('/control/event/{orga}/{event}/questions/add', 200),
    ('/control/event/{orga}/{event}/quotas/', 200),
    ('/control/event/{orga}/{event}/quotas/{quota}/', 200),
    ('/control/event/{orga}/{event}/quotas/{quota}/change', 200),
    ('/control/event/{orga}/{event}/quotas/{quota}/delete', 200),
    ('/control/event/{orga}/{event}/quotas/add', 200),
    ('/control/event/{orga}/{event}/vouchers/', 200),
    ('/control/event/{orga}/{event}/vouchers/tags/', 200),
    ('/control/event/{orga}/{event}/vouchers/rng', 200),
    ('/control/event/{orga}/{event}/vouchers/{voucher}/', 200),
    ('/control/event/{orga}/{event}/vouchers/{voucher}/delete', 200),
    ('/control/event/{orga}/{event}/vouchers/add', 200),
    ('/control/event/{orga}/{event}/vouchers/bulk_add', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/extend', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/contact', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/comment', 405),
    ('/control/event/{orga}/{event}/orders/{order_code}/change', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/locale', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/approve', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/deny', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/payments/{payment}/cancel', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/payments/{payment}/confirm', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/refund', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/refunds/{refund}/cancel', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/refunds/{refund}/process', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/refunds/{refund}/done', 200),
    ('/control/event/{orga}/{event}/orders/{order_code}/', 200),
    ('/control/event/{orga}/{event}/orders/overview/', 200),
    ('/control/event/{orga}/{event}/orders/export/', 200),
    ('/control/event/{orga}/{event}/orders/go', 302),
    ('/control/event/{orga}/{event}/orders/search', 200),
    ('/control/event/{orga}/{event}/orders/', 200),
    ('/control/event/{orga}/{event}/waitinglist/', 200),
    ('/control/event/{orga}/{event}/waitinglist/auto_assign', 405),
])
@pytest.mark.django_db
def test_one_view(logged_in_client, url, expected, event, item, item_category, order, question, quota, voucher):
    with scope(organizer=event.organizer):
        payment = order.payments.first()
        refund = order.refunds.first()
        url = url.format(
            event=event.slug, orga=event.organizer.slug,
            category=item_category.pk,
            item=item.pk,
            order_code=order.code,
            question=question.pk,
            quota=quota.pk,
            voucher=voucher.pk,
            payment=payment.pk,
            refund=refund.pk
        )
    response = logged_in_client.get(url)
    assert response.status_code == expected
