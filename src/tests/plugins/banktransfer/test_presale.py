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
# This file contains Apache-licensed contributions copyrighted by: Flavia Bastos
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from django.core import mail as djmail
from django_countries.fields import Country
from django_scopes import scopes_disabled
from tests.presale.test_orders import BaseOrdersTest

from pretix.base.models import InvoiceAddress, OrderPayment
from pretix.base.services.invoices import generate_invoice


class BanktransferOrdersTest(BaseOrdersTest):
    def test_unknown_order(self):
        response = self.client.post(
            '/%s/%s/banktransfer/ABCDE/123/mail-invoice/' % (self.orga.slug, self.event.slug)
        )
        assert response.status_code == 404
        response = self.client.post(
            '/%s/%s/banktransfer/%s/123/mail-invoice/' % (self.orga.slug, self.event.slug, self.not_my_order.code)
        )
        assert response.status_code == 404

    def test_order_with_no_invoice(self):
        djmail.outbox = []
        response = self.client.post(
            '/%s/%s/banktransfer/%s/%s/mail-invoice/' % (
                self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {'email': 'test@example.org'}
        )
        assert response.status_code == 302

        from django.contrib.messages import get_messages
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert str(messages[0]) == 'No pending bank transfer payment found. Maybe the order has been paid already?'
        assert len(djmail.outbox) == 0

    def test_valid_order(self):
        with scopes_disabled():
            self.event.settings.set('payment_banktransfer_invoice_email', True)
            self.order.payments.create(provider='banktransfer', state=OrderPayment.PAYMENT_STATE_CREATED,
                                       amount=self.order.total)
            InvoiceAddress.objects.create(order=self.order, company="Sample company", country=Country('NZ'))
            generate_invoice(self.order)

        djmail.outbox = []
        response = self.client.post(
            '/%s/%s/banktransfer/%s/%s/mail-invoice/' % (
                self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {'email': 'test@example.org'}
        )
        assert response.status_code == 302

        from django.contrib.messages import get_messages
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert str(messages[0]) == 'Sending the latest invoice via email to test@example.org.'
        assert len(djmail.outbox) == 1
