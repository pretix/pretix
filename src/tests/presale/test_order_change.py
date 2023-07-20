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

import datetime
from decimal import Decimal

from bs4 import BeautifulSoup
from django.test import TestCase
from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.base import extract_form_fields

from pretix.base.models import (
    Event, Item, ItemAddOn, ItemCategory, ItemVariation, Order, OrderPosition,
    Organizer, Question, Quota, SubEventItemVariation,
)
from pretix.base.models.orders import OrderPayment
from pretix.base.reldate import RelativeDate, RelativeDateWrapper


class BaseOrdersTest(TestCase):

    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            presale_end=now() + datetime.timedelta(days=5),
            plugins='pretix.plugins.stripe,pretix.plugins.banktransfer,tests.testdummy',
            live=True
        )
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('ticketoutput_testdummy__enabled', True)

        self.tr = self.event.tax_rules.create(name="VAT", rate=10)
        self.category = ItemCategory.objects.create(event=self.event, name="Everything", position=0)
        self.quota_shirts = Quota.objects.create(event=self.event, name='Shirts', size=2)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', category=self.category, default_price=12)
        self.quota_shirts.items.add(self.shirt)
        self.shirt_red = ItemVariation.objects.create(item=self.shirt, default_price=14, value="Red")
        self.shirt_blue = ItemVariation.objects.create(item=self.shirt, value="Blue")
        self.quota_shirts.variations.add(self.shirt_red)
        self.quota_shirts.variations.add(self.shirt_blue)
        self.quota_tickets = Quota.objects.create(event=self.event, name='Tickets', size=5)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          category=self.category, default_price=23,
                                          admission=True)
        self.quota_tickets.items.add(self.ticket)
        self.event.settings.set('attendee_names_asked', True)
        self.question = Question.objects.create(question='Foo', type=Question.TYPE_STRING, event=self.event,
                                                required=False)
        self.ticket.questions.add(self.question)

        self.order = Order.objects.create(
            status=Order.STATUS_PENDING,
            event=self.event,
            email='admin@localhost',
            datetime=now() - datetime.timedelta(days=3),
            expires=now() + datetime.timedelta(days=11),
            total=Decimal("23"),
            locale='en'
        )
        self.ticket_pos = OrderPosition.objects.create(
            order=self.order,
            item=self.ticket,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={'full_name': "Peter"}
        )
        self.deleted_pos = OrderPosition.objects.create(
            order=self.order,
            item=self.ticket,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={'full_name': "Lukas"},
            canceled=True
        )


class OrderChangeVariationTest(BaseOrdersTest):
    def test_change_not_allowed(self):
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 302

        response = self.client.get(
            '/%s/%s/ticket/%s/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.ticket_pos.positionid, self.ticket_pos.web_secret)
        )
        assert response.status_code == 302

    def test_change_with_checkin(self):
        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_red,
                price=Decimal("14"),
            )
            shirt_pos.checkins.create(list=self.event.checkin_lists.create(name="Test"))
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 302
        self.event.settings.change_allow_user_if_checked_in = True
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 302

    def test_change_variation_paid(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'any'

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_red,
                price=Decimal("14"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_blue.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        shirt_pos.refresh_from_db()
        assert shirt_pos.variation == self.shirt_blue
        assert shirt_pos.price == Decimal('12.00')
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PENDING
        assert self.order.total == Decimal('35.00')

        # Attendee is not allowed
        response = self.client.get(
            '/%s/%s/ticket/%s/%s/%s/change' % (
                self.orga.slug, self.event.slug, self.order.code, self.ticket_pos.positionid, self.ticket_pos.web_secret)
        )
        assert response.status_code == 302

    def test_change_variation_require_higher_price(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'gt'

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_red,
                price=Decimal("14"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_blue.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        assert 'alert-danger' in response.content.decode()

        shirt_pos.variation = self.shirt_blue
        shirt_pos.price = Decimal('12.00')
        shirt_pos.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        shirt_pos.refresh_from_db()
        assert shirt_pos.variation == self.shirt_red
        assert shirt_pos.price == Decimal('14.00')
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PENDING
        assert self.order.total == Decimal('37.00')

        shirt_pos.variation = self.shirt_blue
        shirt_pos.price = Decimal('14.00')
        shirt_pos.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            },
            follow=True
        )
        shirt_pos.refresh_from_db()
        assert 'alert-danger' in response.content.decode()
        assert shirt_pos.variation == self.shirt_blue
        assert shirt_pos.price == Decimal('14.00')

    def test_change_variation_require_higher_equal_price(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'gte'

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_red,
                price=Decimal("14"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_blue.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        assert 'alert-danger' in response.content.decode()

        shirt_pos.variation = self.shirt_blue
        shirt_pos.price = Decimal('12.00')
        shirt_pos.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        shirt_pos.refresh_from_db()
        assert shirt_pos.variation == self.shirt_red
        assert shirt_pos.price == Decimal('14.00')
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PENDING
        assert self.order.total == Decimal('37.00')

        shirt_pos.variation = self.shirt_blue
        shirt_pos.price = Decimal('14.00')
        shirt_pos.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        shirt_pos.refresh_from_db()
        assert 'alert-success' in response.content.decode()
        assert shirt_pos.variation == self.shirt_red
        assert shirt_pos.price == Decimal('14.00')

    def test_change_variation_require_equal_price(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'eq'

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_blue,
                price=Decimal("12"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        assert 'alert-danger' in response.content.decode()

    def test_change_variation_require_same_product(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'any'

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_blue,
                price=Decimal("12"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.ticket.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        assert 'alert-danger' in response.content.decode()

    def test_change_variation_hidden_variations(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'any'
        self.shirt_red.value = "RED SHIRT"
        self.shirt_red.hide_without_voucher = True
        self.shirt_red.save()

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_blue,
                price=Decimal("12"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'RED SHIRT' not in response.content.decode()
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        assert 'alert-danger' in response.content.decode()

    def test_change_variation_hidden_variations_with_voucher(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'any'
        self.shirt_red.value = "RED SHIRT"
        self.shirt_red.hide_without_voucher = True
        self.shirt_red.save()

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_blue,
                voucher=self.event.vouchers.create(code="ABCDE", item=self.shirt),
                price=Decimal("12"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'RED SHIRT' in response.content.decode()
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        shirt_pos.refresh_from_db()
        assert 'alert-success' in response.content.decode()
        assert shirt_pos.variation == self.shirt_red
        assert shirt_pos.price == Decimal('14.00')

    def test_change_variation_hidden_variations_with_useless_voucher(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'any'
        self.shirt_red.value = "RED SHIRT"
        self.shirt_red.hide_without_voucher = True
        self.shirt_red.save()

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_blue,
                voucher=self.event.vouchers.create(code="ABCDE", item=self.shirt, show_hidden_items=False),
                price=Decimal("12"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'RED SHIRT' not in response.content.decode()
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        assert 'alert-danger' in response.content.decode()

    def test_change_variation_require_quota(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'any'

        with scopes_disabled():
            q = self.event.quotas.create(name="s2", size=0)
            q.items.add(self.shirt)
            q.variations.add(self.shirt_red)

        with scopes_disabled():
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_blue,
                price=Decimal("12"),
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        assert response.status_code == 200
        assert 'alert-danger' in response.content.decode()

        q.variations.add(self.shirt_blue)

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/' % (self.orga.slug, self.event.slug, self.order.code,
                                                      self.order.secret),
                             target_status_code=200)
        shirt_pos.refresh_from_db()
        assert shirt_pos.variation == self.shirt_red
        assert shirt_pos.price == Decimal('14.00')

    def test_change_paid_to_pending(self):
        self.event.settings.change_allow_user_variation = True
        self.event.settings.change_allow_user_price = 'any'
        self.order.status = Order.STATUS_PAID
        self.order.save()

        with scopes_disabled():
            self.order.payments.create(provider="manual", amount=Decimal('35.00'), state=OrderPayment.PAYMENT_STATE_CONFIRMED)
            shirt_pos = OrderPosition.objects.create(
                order=self.order,
                item=self.shirt,
                variation=self.shirt_blue,
                price=Decimal("12"),
            )

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'op-{shirt_pos.pk}-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
                f'op-{self.ticket_pos.pk}-itemvar': f'{self.ticket.pk}',
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        self.assertRedirects(response,
                             '/%s/%s/order/%s/%s/pay/change' % (self.orga.slug, self.event.slug, self.order.code,
                                                                self.order.secret),
                             target_status_code=200)
        assert 'The order has been changed. You can now proceed by paying the open amount of €2.00.' in response.content.decode()
        shirt_pos.refresh_from_db()
        assert shirt_pos.variation == self.shirt_red
        assert shirt_pos.price == Decimal('14.00')
        self.order.refresh_from_db()
        assert self.order.status == Order.STATUS_PENDING
        assert self.order.pending_sum == Decimal('2.00')


class OrderChangeAddonsTest(BaseOrdersTest):

    @scopes_disabled()
    def setUp(self):
        super().setUp()

        self.workshopcat = ItemCategory.objects.create(name="Workshops", is_addon=True, event=self.event)
        self.workshopquota = Quota.objects.create(event=self.event, name='Workshop 1', size=5)
        self.workshop1 = Item.objects.create(event=self.event, name='Workshop 1',
                                             category=self.workshopcat, default_price=Decimal('12.00'),
                                             tax_rule=self.tr)
        self.workshop2 = Item.objects.create(event=self.event, name='Workshop 2',
                                             category=self.workshopcat, default_price=Decimal('12.00'),
                                             tax_rule=self.tr)
        self.workshop2a = ItemVariation.objects.create(item=self.workshop2, value='Workshop 2a')
        self.workshop2b = ItemVariation.objects.create(item=self.workshop2, value='Workshop 2b')
        self.workshopquota.items.add(self.workshop1)
        self.workshopquota.items.add(self.workshop2)
        self.workshopquota.variations.add(self.workshop2a)
        self.workshopquota.variations.add(self.workshop2b)
        self.iao = ItemAddOn.objects.create(
            base_item=self.ticket, addon_category=self.workshopcat, max_count=1, min_count=0, multi_allowed=False
        )
        self.event.settings.change_allow_user_addons = True
        self.event.settings.change_allow_user_price = 'any'

    def test_disabled(self):
        self.event.settings.change_allow_user_addons = False
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 302

    def test_no_config(self):
        self.iao.base_item = self.shirt
        self.iao.save()
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 302

    def test_no_change(self):
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
            },
            follow=True
        )
        assert 'alert-info' in response.content.decode()

    def test_add_addon(self):
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}': '1'
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-success' in response.content.decode()

        with scopes_disabled():
            new_pos = self.ticket_pos.addons.get()
            assert new_pos.item == self.workshop1
            assert new_pos.price == Decimal('12.00')
            self.order.refresh_from_db()
            assert self.order.total == Decimal('35.00')

    def test_add_addon_included_in_voucher(self):
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, all_addons_included=True)
            self.ticket_pos.voucher = v
            self.ticket_pos.save()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}': '1'
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-success' in response.content.decode()

        with scopes_disabled():
            new_pos = self.ticket_pos.addons.get()
            assert new_pos.item == self.workshop1
            assert new_pos.price == Decimal('0.00')
            self.order.refresh_from_db()
            assert self.order.total == Decimal('23.00')

    def test_add_addon_free_price(self):
        self.workshop1.free_price = True
        self.workshop1.save()

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}': '1',
                f'cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}_price': '50.00',
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-success' in response.content.decode()

        with scopes_disabled():
            new_pos = self.ticket_pos.addons.get()
            assert new_pos.item == self.workshop1
            assert new_pos.price == Decimal('50.00')
            self.order.refresh_from_db()
            assert self.order.total == Decimal('73.00')

    def test_add_addon_free_price_net(self):
        self.event.settings.display_net_prices = True
        self.workshop1.free_price = True
        self.workshop1.save()

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}': '1',
                f'cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}_price': '50.00',
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-success' in response.content.decode()

        with scopes_disabled():
            new_pos = self.ticket_pos.addons.get()
            assert new_pos.item == self.workshop1
            assert new_pos.price == Decimal('55.00')
            self.order.refresh_from_db()
            assert self.order.total == Decimal('78.00')

    def test_remove_addon(self):
        with scopes_disabled():
            OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("12"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            self.order.total += Decimal("12")
            self.order.save()

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')[0].attrs['checked']

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-success' in response.content.decode()

        with scopes_disabled():
            a = self.ticket_pos.addons.get()
            assert a.canceled
            self.order.refresh_from_db()
            assert self.order.total == Decimal('23.00')

    def test_remove_addon_checked_in(self):
        with scopes_disabled():
            self.event.settings.change_allow_user_if_checked_in = True
            op = OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("12"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            op.checkins.create(list=self.event.checkin_lists.create(name="Test"))
            self.order.total += Decimal("12")
            self.order.save()

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')[0].attrs['checked']

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert 'alert-danger' in response.content.decode()
        assert 'You cannot remove the position' in response.content.decode()

    def test_increase_existing_addon_free_price_net(self):
        self.event.settings.display_net_prices = True
        self.iao.multi_allowed = True
        self.iao.max_count = 2
        self.iao.save()
        self.workshop1.free_price = True
        self.workshop1.save()

        with scopes_disabled():
            OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("55"),
                tax_rule=self.tr,
                tax_rate=Decimal("10"),
                tax_value=Decimal("5"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            self.order.total += Decimal("55")
            self.order.save()

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')[0].attrs['value'] == '1'
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}_price]')[0].attrs['value'] == '50.00'

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}': '2',
                f'cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}_price': '100.00',
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-success' in response.content.decode()

        with scopes_disabled():
            # only the price of the new addon is changed!
            assert self.ticket_pos.addons.count() == 2
            a = self.ticket_pos.addons.first()
            assert a.item == self.workshop1
            assert a.price == Decimal('55.00')
            a = self.ticket_pos.addons.last()
            assert a.item == self.workshop1
            assert a.price == Decimal('110.00')

    def test_change_addon(self):
        with scopes_disabled():
            OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("12"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            self.order.total += Decimal("12")
            self.order.save()

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')[0].attrs['checked']

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-success' in response.content.decode()

        with scopes_disabled():
            # todo: should this keep questions?
            a = self.ticket_pos.addons.get(canceled=False)
            assert a.item == self.workshop2
            assert a.variation == self.workshop2a

    def test_paid_to_pending_expiry_date(self):
        self.order.status = Order.STATUS_PAID
        self.order.expires = now() - datetime.timedelta(days=12)
        self.order.save()
        with scopes_disabled():
            self.order.payments.create(
                provider="manual",
                amount=self.order.total,
                state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            )
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}': '1'
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-success' in response.content.decode()

        with scopes_disabled():
            new_pos = self.ticket_pos.addons.get()
            assert new_pos.item == self.workshop1
            assert new_pos.price == Decimal('12.00')
            self.order.refresh_from_db()
            assert self.order.total == Decimal('35.00')
            assert self.order.pending_sum == Decimal('12.00')
            assert self.order.expires > now()

    def test_quota_sold_out(self):
        self.workshopquota.size = 0
        self.workshopquota.save()

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert not doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}': '1'
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-danger' in response.content.decode()

        with scopes_disabled():
            assert self.ticket_pos.addons.count() == 0

    def test_quota_hide_sold_out_do_not_hide_initial(self):
        self.event.settings.hide_sold_out = True
        self.workshopquota.size = 1
        self.workshopquota.save()

        with scopes_disabled():
            OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("12"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            self.order.total += Decimal("12")
            self.order.save()

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()
        assert 'Workshop 2' not in response.content.decode()

    def test_quota_sold_out_replace(self):
        self.workshopquota.size = 1
        self.workshopquota.save()

        with scopes_disabled():
            OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("12"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            self.order.total += Decimal("12")
            self.order.save()

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')[0].attrs['checked']
        # TODO: Technically, it is allowed to do this change, although the frontend currently does not allow it
        # We test for the backend behaviour anyways
        assert not doc.select(f'input[name=cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}]')

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-success' in response.content.decode()

        with scopes_disabled():
            a = self.ticket_pos.addons.get(canceled=False)
            assert a.item == self.workshop2
            assert a.variation == self.workshop2a

    def _assert_ws2a_not_allowed(self):
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 2a' not in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert not doc.select(f'input[name=cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}]')

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode() or 'alert-info' in response.content.decode()

        with scopes_disabled():
            assert self.ticket_pos.addons.count() == 0

    def test_voucher_required(self):
        self.workshop2.require_voucher = True
        self.workshop2.save()
        self._assert_ws2a_not_allowed()

    def test_forbidden_require_bundling(self):
        self.workshop2.require_bundling = True
        self.workshop2.save()
        self._assert_ws2a_not_allowed()

    def test_forbidden_sales_channel(self):
        self.workshop2.sales_channels = ['pretixpos']
        self.workshop2.save()
        self._assert_ws2a_not_allowed()

    def test_forbidden_var_sales_channel(self):
        self.workshop2a.sales_channels = ['pretixpos']
        self.workshop2a.save()
        self._assert_ws2a_not_allowed()

    def test_forbidden_inactive(self):
        self.workshop2.active = False
        self.workshop2.save()
        self._assert_ws2a_not_allowed()

    def test_forbidden_var_inactive(self):
        self.workshop2a.active = False
        self.workshop2a.save()
        self._assert_ws2a_not_allowed()

    def test_forbidden_over(self):
        self.workshop2.available_until = now() - datetime.timedelta(days=3)
        self.workshop2.save()
        self._assert_ws2a_not_allowed()

    def test_forbidden_var_over(self):
        self.workshop2a.available_until = now() - datetime.timedelta(days=3)
        self.workshop2a.save()
        self._assert_ws2a_not_allowed()

    def test_forbidden_membership(self):
        self.workshop2a.require_membership = True
        self.workshop2a.save()
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-danger' in response.content.decode()

    @scopes_disabled()
    def _subevent_setup(self):
        self.event.has_subevents = True
        self.event.save()
        se = self.event.subevents.create(name="Date", date_from=now())
        self.ticket_pos.subevent = se
        self.ticket_pos.save()
        self.workshopquota.subevent = se
        self.workshopquota.save()
        return se

    def test_forbidden_disabled_for_subevent(self):
        se = self._subevent_setup()
        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 2' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}]')

        SubEventItemVariation.objects.create(subevent=se, variation=self.workshop2a, disabled=True)

        self._assert_ws2a_not_allowed()

    def test_presale_has_ended(self):
        self.event.presale_end = now() - datetime.timedelta(days=1)
        self.event.save()

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 2a' in response.content.decode()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()
        assert 'has ended' in response.content.decode()

        with scopes_disabled():
            assert self.ticket_pos.addons.count() == 0

    def test_presale_last_payment_term_only_relevant_if_additional_charge(self):
        self.order.status = Order.STATUS_PAID
        self.order.save()
        self._subevent_setup()
        self.event.settings.set('payment_term_last', RelativeDateWrapper(
            RelativeDate(days_before=2, time=None, base_date_name='date_from', minutes_before=None)
        ))

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 2a' in response.content.decode()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()
        assert 'no longer being accepted' in response.content.decode()

        with scopes_disabled():
            assert self.ticket_pos.addons.count() == 0

        self.workshop2a.default_price = Decimal('0.00')
        self.workshop2a.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-success' in response.content.decode()

        with scopes_disabled():
            new_pos = self.ticket_pos.addons.get()
            assert new_pos.item == self.workshop2
            assert new_pos.price == Decimal('0.00')
            self.order.refresh_from_db()
            assert self.order.total == Decimal('23.00')

    def test_multi_allowed_and_max_count_enforced(self):
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '2'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()

        self.iao.max_count = 2
        self.iao.multi_allowed = True
        self.iao.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '2'
            },
            follow=True
        )
        assert 'alert-danger' not in response.content.decode()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '3'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()

    def test_min_count_enforced(self):
        self.iao.min_count = 1
        self.iao.save()

        with scopes_disabled():
            OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("12"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            self.order.total += Decimal("12")
            self.order.save()

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')[0].attrs['checked']

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()

    def test_max_per_order_enforced(self):
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '2'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()

        self.workshop2.max_per_order = 2
        self.workshop2.save()
        self.iao.multi_allowed = True
        self.iao.max_count = 10
        self.iao.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '2'
            },
            follow=True
        )
        assert 'alert-danger' not in response.content.decode()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '3'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()

    def test_min_per_order_enforced(self):
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '2'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()

        self.workshop2.min_per_order = 2
        self.workshop2.save()
        self.iao.multi_allowed = True
        self.iao.max_count = 10
        self.iao.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '2'
            },
            follow=True
        )
        print(response.content.decode())
        assert 'alert-danger' not in response.content.decode()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()

    def test_allow_user_price_gte(self):
        self.event.settings.change_allow_user_price = 'gte'
        with scopes_disabled():
            OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("12"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            self.order.total += Decimal("12")
            self.order.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()
        assert 'reduces' in response.content.decode()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                'confirm': 'true'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()
        assert 'reduces' in response.content.decode()
        self.order.refresh_from_db()
        assert self.order.total == Decimal('35.00')

    def test_allow_user_price_eq(self):
        self.event.settings.change_allow_user_price = 'eq'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()
        assert 'changes' in response.content.decode()

        self.workshop2a.default_price = Decimal('0.00')
        self.workshop2a.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        assert 'alert-danger' not in response.content.decode()

    def test_allow_user_price_gt(self):
        self.event.settings.change_allow_user_price = 'gt'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        assert 'alert-danger' not in response.content.decode()

        self.workshop2a.default_price = Decimal('0.00')
        self.workshop2a.save()

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()
        assert 'increases' in response.content.decode()

    def test_ignore_bundled_positions(self):
        with scopes_disabled():
            OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("12"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            self.order.total += Decimal("12")
            OrderPosition.objects.create(
                order=self.order,
                item=self.workshop2,
                variation=self.workshop2a,
                is_bundled=True,
                price=Decimal("12"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            self.order.total += Decimal("12")
            self.order.save()

        response = self.client.get(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret)
        )
        assert response.status_code == 200
        assert 'Workshop 1' in response.content.decode()

        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(f'input[name=cp_{self.ticket_pos.pk}_item_{self.workshop1.pk}]')[0].attrs['checked']

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret),
            {
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )
        assert 'alert-success' in response.content.decode()

        with scopes_disabled():
            a = self.ticket_pos.addons.get(item=self.workshop1)
            assert a.canceled
            a = self.ticket_pos.addons.get(item=self.workshop2)
            assert not a.canceled
            self.order.refresh_from_db()
            assert self.order.total == Decimal('35.00')

    def test_refund_auto(self):
        self.event.settings.cancel_allow_user_paid_refund_as_giftcard = 'off'
        with scopes_disabled():
            OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("12"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            self.order.status = Order.STATUS_PAID
            self.order.total += Decimal("12")
            self.order.save()
            self.order.payments.create(provider='testdummy_partialrefund', amount=self.order.total, state=OrderPayment.PAYMENT_STATE_CONFIRMED)

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {}, follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )

        with scopes_disabled():
            a = self.ticket_pos.addons.get()
            assert a.canceled
            self.order.refresh_from_db()
            assert self.order.total == Decimal('23.00')
            assert self.order.refunds.exists()

    def test_refund_manually(self):
        self.event.settings.cancel_allow_user_paid_refund_as_giftcard = 'manually'
        with scopes_disabled():
            OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("12"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            self.order.status = Order.STATUS_PAID
            self.order.total += Decimal("12")
            self.order.save()
            self.order.payments.create(provider='testdummy_partialrefund', amount=self.order.total, state=OrderPayment.PAYMENT_STATE_CONFIRMED)

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {}, follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )

        with scopes_disabled():
            a = self.ticket_pos.addons.get()
            assert a.canceled
            self.order.refresh_from_db()
            assert self.order.total == Decimal('23.00')
            assert not self.order.refunds.exists()

    def test_refund_giftcard(self):
        self.event.settings.cancel_allow_user_paid_refund_as_giftcard = 'force'
        with scopes_disabled():
            OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("12"),
                addon_to=self.ticket_pos,
                attendee_name_parts={'full_name': "Peter"}
            )
            self.order.status = Order.STATUS_PAID
            self.order.total += Decimal("12")
            self.order.save()
            self.order.payments.create(provider='testdummy_partialrefund', amount=self.order.total, state=OrderPayment.PAYMENT_STATE_CONFIRMED)

        response = self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), {}, follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )

        with scopes_disabled():
            a = self.ticket_pos.addons.get()
            assert a.canceled
            self.order.refresh_from_db()
            assert self.order.total == Decimal('23.00')
            r = self.order.refunds.get()
            assert r.provider == 'giftcard'

    def test_attendee(self):
        self.workshop2a.default_price = Decimal('0.00')
        self.workshop2a.save()
        self.event.settings.change_allow_attendee = True
        response = self.client.post(
            '/%s/%s/ticket/%s/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.ticket_pos.positionid, self.ticket_pos.web_secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        self.client.post(
            '/%s/%s/order/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.order.secret), form_data, follow=True
        )

        with scopes_disabled():
            a = self.ticket_pos.addons.get()
            assert a.variation == self.workshop2a

    def test_attendee_limited_to_own_ticket(self):
        with scopes_disabled():
            ticket_pos2 = OrderPosition.objects.create(
                order=self.order,
                item=self.ticket,
                variation=None,
                price=Decimal("23"),
                attendee_name_parts={'full_name': "Peter"}
            )
        self.event.settings.change_allow_attendee = True
        response = self.client.post(
            '/%s/%s/ticket/%s/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.ticket_pos.positionid, self.ticket_pos.web_secret),
            {
                f'cp_{ticket_pos2.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        assert 'did not make any changes' in response.content.decode()

    def test_attendee_needs_to_keep_price(self):
        self.event.settings.change_allow_user_price = 'any'  # ignored, for attendees its always "eq"
        self.event.settings.change_allow_attendee = True
        response = self.client.post(
            '/%s/%s/ticket/%s/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.ticket_pos.positionid, self.ticket_pos.web_secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        assert 'alert-danger' in response.content.decode()
        assert 'changes' in response.content.decode()

        self.workshop2a.default_price = Decimal('0.00')
        self.workshop2a.save()

        response = self.client.post(
            '/%s/%s/ticket/%s/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.ticket_pos.positionid, self.ticket_pos.web_secret),
            {
                f'cp_{self.ticket_pos.pk}_variation_{self.workshop2.pk}_{self.workshop2a.pk}': '1'
            },
            follow=True
        )
        assert 'alert-danger' not in response.content.decode()

    def test_attendee_price_hidden(self):
        self.event.settings.change_allow_attendee = True
        response = self.client.get(
            '/%s/%s/ticket/%s/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.ticket_pos.positionid, self.ticket_pos.web_secret),
            follow=True
        )
        assert '€' not in response.content.decode()
        self.event.settings.hide_prices_from_attendees = False
        response = self.client.get(
            '/%s/%s/ticket/%s/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.ticket_pos.positionid, self.ticket_pos.web_secret),
            follow=True
        )
        assert '€' in response.content.decode()

    def test_attendee_change_of_addons_does_not_affect_other_positions(self):
        with scopes_disabled():
            ticket_pos2 = OrderPosition.objects.create(
                order=self.order,
                item=self.ticket,
                variation=None,
                price=Decimal("23"),
                attendee_name_parts={'full_name': "Peter"}
            )
            a1 = OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("0"),
                addon_to=self.ticket_pos,
            )
            a2 = OrderPosition.objects.create(
                order=self.order,
                item=self.workshop1,
                variation=None,
                price=Decimal("0"),
                addon_to=ticket_pos2,
            )

        self.event.settings.change_allow_attendee = True

        response = self.client.get(
            '/%s/%s/ticket/%s/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.ticket_pos.positionid, self.ticket_pos.web_secret),
        )
        doc = BeautifulSoup(response.content.decode(), "lxml")
        form_data = extract_form_fields(doc.select('.main-box form')[0])
        form_data['confirm'] = 'true'
        response = self.client.post(
            '/%s/%s/ticket/%s/%s/%s/change' % (self.orga.slug, self.event.slug, self.order.code, self.ticket_pos.positionid, self.ticket_pos.web_secret),
            form_data, follow=True
        )
        assert 'alert-success' in response.content.decode()

        a1.refresh_from_db()
        a2.refresh_from_db()
        assert not a1.canceled
        assert not a2.canceled
