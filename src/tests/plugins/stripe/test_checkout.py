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
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import datetime

import pytest
from django.utils.timezone import now

from pretix.base.models import (
    CartPosition, Event, Item, ItemCategory, Organizer, Quota,
)
from pretix.testutils.sessions import add_cart_session, get_cart_session_key


class MockedCharge():
    status = ''
    paid = False
    id = 'ch_123345345'

    def refresh(self):
        pass


class Object():
    pass


class MockedPaymentintent():
    status = ''
    id = 'pi_1EUon12Tb35ankTnZyvC3SdE'
    charges = Object()
    charges.data = [MockedCharge()]
    last_payment_error = None


@pytest.fixture
def env(client):
    orga = Organizer.objects.create(name='CCC', slug='ccc')
    event = Event.objects.create(
        organizer=orga, name='30C3', slug='30c3',
        date_from=datetime.datetime(now().year + 1, 12, 26, tzinfo=datetime.timezone.utc),
        plugins='pretix.plugins.stripe',
        live=True
    )
    category = ItemCategory.objects.create(event=event, name="Everything", position=0)
    quota_tickets = Quota.objects.create(event=event, name='Tickets', size=5)
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 category=category, default_price=23, admission=True)
    quota_tickets.items.add(ticket)
    event.settings.set('attendee_names_asked', False)
    event.settings.set('payment_stripe__enabled', True)
    add_cart_session(client, event, {'email': 'admin@localhost'})
    return client, ticket


@pytest.mark.django_db
def test_payment(env, monkeypatch):
    def paymentintent_create(**kwargs):
        assert kwargs['amount'] == 1337
        assert kwargs['currency'] == 'eur'
        assert kwargs['payment_method'] == 'pm_189fTT2eZvKYlo2CvJKzEzeu'
        c = MockedPaymentintent()
        c.status = 'succeeded'
        c.charges.data[0].paid = True
        setattr(paymentintent_create, 'called', True)
        return c

    monkeypatch.setattr("stripe.PaymentIntent.create", paymentintent_create)

    client, ticket = env
    ticket.default_price = 13.37
    ticket.save()
    session_key = get_cart_session_key(client, ticket.event)
    CartPosition.objects.create(
        event=ticket.event, cart_id=session_key, item=ticket,
        price=13.37, expires=now() + datetime.timedelta(minutes=10)
    )
    client.get('/%s/%s/checkout/payment/' % (ticket.event.organizer.slug, ticket.event.slug), follow=True)
    client.post('/%s/%s/checkout/questions/' % (ticket.event.organizer.slug, ticket.event.slug), {
        'email': 'admin@localhost'
    }, follow=True)
    paymentintent_create.called = False
    response = client.post('/%s/%s/checkout/payment/' % (ticket.event.organizer.slug, ticket.event.slug), {
        'payment': 'stripe',
        'stripe_card_payment_method_id': 'pm_189fTT2eZvKYlo2CvJKzEzeu',
        'stripe_card_brand': 'visa',
        'stripe_card_last4': '1234'
    }, follow=True)
    assert not paymentintent_create.called
    assert response.status_code == 200
    assert 'alert-danger' not in response.rendered_content
    response = client.post('/%s/%s/checkout/confirm/' % (ticket.event.organizer.slug, ticket.event.slug), {
    }, follow=True)
    assert response.status_code == 200
