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
# This file contains Apache-licensed contributions copyrighted by: Daniel, Flavia Bastos, Jahongir
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from datetime import timedelta
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup
from django.core import mail
from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.base import extract_form_fields

from pretix.base.models import (
    Event, Item, Order, OrderPayment, OrderPosition, Organizer, Team, User,
)


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.stripe,tests.testdummy'
    )
    event.settings.set('ticketoutput_testdummy__enabled', True)
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    t = Team.objects.create(organizer=o, can_view_orders=True, can_change_orders=True, can_manage_customers=True)
    t.members.add(user)
    t.limit_events.add(event)
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 category=None, default_price=23,
                                 admission=True, personalized=True)
    event.settings.set('attendee_names_asked', True)
    event.settings.set('locales', ['en', 'de'])
    return event, user, ticket


@pytest.fixture
def order1(env):
    o = Order.objects.create(
        code='FOO', event=env[0], email='foo@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=14, locale='en'
    )
    o.payments.create(
        amount=o.total, provider='banktransfer', state=OrderPayment.PAYMENT_STATE_PENDING
    )
    OrderPosition.objects.create(
        order=o,
        item=env[2],
        variation=None,
        price=Decimal("14"),
        attendee_name_parts={'full_name': "Peter", "_scheme": "full"}
    )
    return o


@pytest.fixture
def order2(env):
    o = Order.objects.create(
        code='BAR', event=env[0], email='bar@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=14, locale='en'
    )
    o.payments.create(
        amount=o.total, provider='banktransfer', state=OrderPayment.PAYMENT_STATE_PENDING
    )
    OrderPosition.objects.create(
        order=o,
        item=env[2],
        variation=None,
        price=Decimal("14"),
        attendee_name_parts={'full_name': "Peter", "_scheme": "full"}
    )
    return o


def _run_bulk_action(client, urlname, filter_post_data, submit_post_data):
    resp = client.post(f'/control/event/dummy/dummy/orders/bulk/{urlname}', filter_post_data)
    doc = BeautifulSoup(resp.content, "lxml")
    data = extract_form_fields(doc.select('.container-fluid form')[0])
    for k, v in submit_post_data.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    resp = client.post(f'/control/event/dummy/dummy/orders/bulk/{urlname}', data, follow=True)
    assert b'alert-success' in resp.content


@pytest.mark.django_db
def test_order_bulk_approve_explicit_id(client, env, order1, order2):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        order1.require_approval = True
        order1.save()
        order2.require_approval = True
        order2.save()

    _run_bulk_action(client, 'approve', {'order': order1.pk}, {'operation': 'confirm'})

    order1.refresh_from_db()
    order2.refresh_from_db()
    assert not order1.require_approval
    assert order1.status == Order.STATUS_PENDING
    assert order2.require_approval


@pytest.mark.django_db
def test_order_bulk_approve_search_form_all(client, env, order1, order2):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        order1.require_approval = True
        order1.save()
        order2.require_approval = True
        order2.save()

    _run_bulk_action(client, 'approve', {'query': 'FOO', '__ALL': 'on'}, {'operation': 'confirm'})

    order1.refresh_from_db()
    order2.refresh_from_db()
    assert not order1.require_approval
    assert order1.status == Order.STATUS_PENDING
    assert order2.require_approval


@pytest.mark.django_db
def test_order_bulk_approve_expert_search_form_all(client, env, order1, order2):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        order1.require_approval = True
        order1.save()
        order2.require_approval = True
        order2.save()

    _run_bulk_action(client, 'approve', {'expert-email': 'foo@dummy.test', '__ALL': 'on'}, {'operation': 'confirm'})

    order1.refresh_from_db()
    order2.refresh_from_db()
    assert not order1.require_approval
    assert order1.status == Order.STATUS_PENDING
    assert order2.require_approval


@pytest.mark.django_db
def test_order_bulk_approve_ignore_wrong_state(client, env, order1, order2):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        order1.require_approval = True
        order1.save()
        order2.require_approval = True
        order2.status = Order.STATUS_CANCELED
        order2.save()

    resp = client.post('/control/event/dummy/dummy/orders/bulk/approve', {'__ALL': 'on'})
    assert b'FOO' in resp.content
    assert b'BAR' not in resp.content

    _run_bulk_action(client, 'approve', {'__ALL': 'on'}, {'operation': 'confirm'})

    order1.refresh_from_db()
    order2.refresh_from_db()
    assert not order1.require_approval
    assert order2.require_approval


@pytest.mark.django_db
def test_order_bulk_deny_ignore_wrong_state(client, env, order1, order2):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        order1.require_approval = True
        order1.save()
        order2.require_approval = False
        order2.save()
    mail.outbox = []

    resp = client.post('/control/event/dummy/dummy/orders/bulk/deny', {'__ALL': 'on'})
    assert b'FOO' in resp.content
    assert b'BAR' not in resp.content

    _run_bulk_action(client, 'deny', {'__ALL': 'on'}, {'operation': 'confirm', 'bulkactionform-send_email': 'on'})
    assert len(mail.outbox) == 1

    order1.refresh_from_db()
    order2.refresh_from_db()
    assert order1.require_approval
    assert order1.status == Order.STATUS_CANCELED
    assert not order2.require_approval
    assert order2.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_order_bulk_deny_send_no_mail(client, env, order1, order2):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        order1.require_approval = True
        order1.save()
        order2.require_approval = False
        order2.save()

    mail.outbox = []
    _run_bulk_action(client, 'deny', {'__ALL': 'on'}, {'operation': 'confirm', 'bulkactionform-send_email': None})
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_order_bulk_expire_ignore_wrong_state(client, env, order1, order2):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        order1.expires = now() - timedelta(days=1)
        order1.save()
        order2.expires = now() + timedelta(days=1)
        order2.save()
    mail.outbox = []

    resp = client.post('/control/event/dummy/dummy/orders/bulk/expire', {'__ALL': 'on'})
    assert b'FOO' in resp.content
    assert b'BAR' not in resp.content

    _run_bulk_action(client, 'expire', {'__ALL': 'on'}, {'operation': 'confirm'})

    order1.refresh_from_db()
    order2.refresh_from_db()
    assert order1.status == Order.STATUS_EXPIRED
    assert order2.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_order_bulk_delete_ignore_wrong_state(client, env, order1, order2):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        order1.testmode = True
        order1.save()
        order2.testmode = False
        order2.save()
    mail.outbox = []

    resp = client.post('/control/event/dummy/dummy/orders/bulk/delete', {'__ALL': 'on'})
    assert b'FOO' in resp.content
    assert b'BAR' not in resp.content

    _run_bulk_action(client, 'delete', {'__ALL': 'on'}, {'operation': 'confirm'})

    with scopes_disabled():
        assert Order.objects.get() == order2


@pytest.mark.django_db
def test_order_bulk_overpaid_refund_explicit_id(client, env, order1, order2):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        payment1 = order1.payments.first()
        payment1.state = OrderPayment.PAYMENT_STATE_CONFIRMED
        payment1.info_data = {"payer": "Dummy Dummy", "iban": "DE02120300000000202051"}
        payment1.save()
        order1.payments.create(
            amount=2, provider='banktransfer', state=OrderPayment.PAYMENT_STATE_CONFIRMED
        )

    _run_bulk_action(client, 'refund_overpaid', {'order': order1.pk}, {'operation': 'confirm'})

    order1.refresh_from_db()
    order2.refresh_from_db()
    with scopes_disabled():
        assert order1.refunds.exists()
        assert order1.refunds.get().amount == Decimal('2.00')


@pytest.mark.django_db
def test_order_bulk_overpaid_refund_ignores_non_refundable(client, env, order1, order2):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        o1_payment1 = order1.payments.first()
        o1_payment1.state = OrderPayment.PAYMENT_STATE_CONFIRMED
        o1_payment1.save()
        order1.payments.create(
            amount=2, provider='banktransfer', state=OrderPayment.PAYMENT_STATE_CONFIRMED
        )
        o2_payment1 = order1.payments.first()
        o2_payment1.provider = "manual"
        o2_payment1.save()
        order2.payments.create(
            amount=2, provider='banktransfer', state=OrderPayment.PAYMENT_STATE_CONFIRMED
        )

    _run_bulk_action(client, 'refund_overpaid', {'__ALL': 'on'}, {'operation': 'confirm'})

    order1.refresh_from_db()
    order2.refresh_from_db()
    with scopes_disabled():
        assert not order1.refunds.exists()
        assert not order2.refunds.exists()
