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


@pytest.fixture
def env(client):
    orga = Organizer.objects.create(name='CCC', slug='ccc')
    event = Event.objects.create(
        organizer=orga, name='30C3', slug='30c3',
        date_from=datetime.datetime(now().year + 1, 12, 26, tzinfo=datetime.timezone.utc),
        plugins='pretix.plugins.paypal2',
        live=True
    )
    category = ItemCategory.objects.create(event=event, name="Everything", position=0)
    quota_tickets = Quota.objects.create(event=event, name='Tickets', size=5)
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 category=category, default_price=23, admission=True)
    quota_tickets.items.add(ticket)
    event.settings.set('attendee_names_asked', False)
    event.settings.set('payment_paypal__enabled', True)
    event.settings.set('payment_paypal__fee_abs', 3)
    event.settings.set('payment_paypal_endpoint', 'sandbox')
    event.settings.set('payment_paypal_client_id', '12345')
    event.settings.set('payment_paypal_secret', '12345')
    add_cart_session(client, event, {'email': 'admin@localhost'})
    return client, ticket


class Object():
    pass


def get_test_order():
    return {'id': '04F89033701558004',
            'intent': 'CAPTURE',
            'status': 'APPROVED',
            'purchase_units': [{'reference_id': 'default',
                                'amount': {'currency_code': 'EUR', 'value': '43.59'},
                                'payee': {'merchant_id': 'G6R2B9YXADKWW'},
                                'description': 'Event tickets for PayPal v2',
                                'custom_id': 'PAYPALV2',
                                'soft_descriptor': 'MARTINFACIL'}],
            'payer': {'name': {'given_name': 'test', 'surname': 'buyer'},
                      'email_address': 'dummy@dummy.dummy',
                      'payer_id': 'Q739JNKWH67HE',
                      'address': {'country_code': 'DE'}},
            'create_time': '2022-04-28T13:10:58Z',
            'links': [{'href': 'https://api.sandbox.paypal.com/v2/checkout/orders/04F89033701558004',
                       'rel': 'self',
                       'method': 'GET'},
                      {'href': 'https://api.sandbox.paypal.com/v2/checkout/orders/04F89033701558004',
                       'rel': 'update',
                       'method': 'PATCH'},
                      {'href': 'https://api.sandbox.paypal.com/v2/checkout/orders/04F89033701558004/capture',
                       'rel': 'capture',
                       'method': 'POST'}]}


@pytest.mark.django_db
def test_payment(env, monkeypatch):
    def init_api(self):
        class Client():
            environment = Object()
            environment.client_id = '12345'
            environment.merchant_id = 'G6R2B9YXADKWW'

            def execute(self, request):
                response = Object()
                response.result = Object()
                response.result.status = 'APPROVED'
                return response

        self.client = Client()

    order = get_test_order()
    monkeypatch.setattr("paypalcheckoutsdk.orders.OrdersGetRequest", lambda *args: order)
    monkeypatch.setattr("pretix.plugins.paypal2.payment.PaypalMethod.init_api", init_api)

    client, ticket = env
    session_key = get_cart_session_key(client, ticket.event)
    CartPosition.objects.create(
        event=ticket.event, cart_id=session_key, item=ticket,
        price=23, expires=now() + datetime.timedelta(minutes=10)
    )
    client.get('/%s/%s/checkout/payment/' % (ticket.event.organizer.slug, ticket.event.slug), follow=True)
    client.post('/%s/%s/checkout/questions/' % (ticket.event.organizer.slug, ticket.event.slug), {
        'email': 'admin@localhost'
    }, follow=True)

    session = client.session
    session['payment_paypal_oid'] = '04F89033701558004'
    session.save()

    response = client.post('/%s/%s/checkout/payment/' % (ticket.event.organizer.slug, ticket.event.slug), {
        'payment': 'paypal',
        'payment_paypal_wallet_oid': '04F89033701558004',
        'payment_paypal_wallet_payer': 'Q739JNKWH67HE',
    })
    assert response['Location'] == '/ccc/30c3/checkout/confirm/'
