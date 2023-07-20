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

import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    CartPosition, Event, Item, OrderPosition, Organizer, Quota, Voucher,
)
from pretix.base.services.orders import _perform_order
from pretix.testutils.sessions import get_cart_session_key


class BundlePricesTest(TestCase):
    # This is an end to end test in addition to what's already tested in
    # cart and checkout tests to ensure consistency

    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(now().year + 1, 12, 26, tzinfo=datetime.timezone.utc),
            live=True,
            plugins="pretix.plugins.banktransfer",
            sales_channels=['web', 'bar']
        )
        self.tr19 = self.event.tax_rules.create(rate=Decimal('19.00'))
        self.tr7 = self.event.tax_rules.create(rate=Decimal('7.00'))

        self.food = Item.objects.create(event=self.event, name='Food',
                                        default_price=5, require_bundling=True,
                                        tax_rule=self.tr7)

        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          default_price=23,
                                          tax_rule=self.tr19)

        self.bundle = self.ticket.bundles.create(
            bundled_item=self.food, designated_price=Decimal('10.00'),
        )

        self.quota_all = Quota.objects.create(event=self.event, name='All', size=None)
        self.quota_all.items.add(self.ticket)
        self.quota_all.items.add(self.food)

        self.session_key = get_cart_session_key(self.client, self.event)

    def _manual_payment(self):
        return [{
            "id": "test1",
            "provider": "manual",
            "max_value": None,
            "min_value": None,
            "multi_use_supported": False,
            "info_data": {},
        }]

    def test_simple_case(self):
        # Verify correct price displayed on event page
        response = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertContains(response, '23.00')

        # Verify correct price being added to cart
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1'
        }, follow=True)
        with scopes_disabled():
            cp1 = CartPosition.objects.get(is_bundled=False)
            cp2 = CartPosition.objects.get(is_bundled=True)

        assert cp1.price == Decimal('13.00')
        assert cp1.item == self.ticket
        assert cp2.price == Decimal('10.00')
        assert cp2.item == self.food

        # Make sure cart expires
        cp1.expires = now() - datetime.timedelta(minutes=120)
        cp1.save()
        cp2.expires = now() - datetime.timedelta(minutes=120)
        cp2.save()

        # Verify price is kept if cart expires and order is sent
        with scopes_disabled():
            _perform_order(self.event, self._manual_payment(), [cp1.pk, cp2.pk], 'admin@example.org', 'en', None, {}, 'web')
            op1 = OrderPosition.objects.get(is_bundled=False)
            op2 = OrderPosition.objects.get(is_bundled=True)
        assert op1.price == Decimal('13.00')
        assert op1.item == self.ticket
        assert op1.tax_rate == Decimal('19.00')
        assert op2.price == Decimal('10.00')
        assert op2.item == self.food
        assert op2.tax_rate == Decimal('7.00')

    def test_voucher_includes_bundles(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('0.00'), event=self.event, price_mode='set',
                                       all_bundles_included=True)

        # Verify correct price displayed on event page
        response = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertContains(response, '23.00')

        # Verify correct price being added to cart
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            '_voucher_code': v.code
        }, follow=True)
        with scopes_disabled():
            cp1 = CartPosition.objects.get(is_bundled=False)
            cp2 = CartPosition.objects.get(is_bundled=True)

        assert cp1.price == Decimal('0.00')
        assert cp1.item == self.ticket
        assert cp2.price == Decimal('0.00')
        assert cp2.item == self.food

        # Make sure cart expires
        cp1.expires = now() - datetime.timedelta(minutes=120)
        cp1.save()
        cp2.expires = now() - datetime.timedelta(minutes=120)
        cp2.save()

        # Verify price is kept if cart expires and order is sent
        with scopes_disabled():
            _perform_order(self.event, self._manual_payment(), [cp1.pk, cp2.pk], 'admin@example.org', 'en', None, {}, 'web')
            op1 = OrderPosition.objects.get(is_bundled=False)
            op2 = OrderPosition.objects.get(is_bundled=True)
        assert op1.price == Decimal('0.00')
        assert op1.item == self.ticket
        assert op1.tax_rate == Decimal('19.00')
        assert op2.price == Decimal('0.00')
        assert op2.item == self.food
        assert op2.tax_rate == Decimal('7.00')

    def test_net_price_definitions(self):
        self.tr19.price_includes_tax = False
        self.tr19.save()
        self.tr7.price_includes_tax = False
        self.tr7.save()
        # Verify correct price displayed on event page
        response = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertContains(response, '27.37')

        # Verify correct price displayed on event page in net mode
        self.event.settings.display_net_prices = True
        response = self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.assertContains(response, '23.95')

        # Verify correct price being added to cart
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1'
        }, follow=True)
        with scopes_disabled():
            cp1 = CartPosition.objects.get(is_bundled=False)
            cp2 = CartPosition.objects.get(is_bundled=True)

        assert cp1.price == Decimal('17.37')
        assert cp1.item == self.ticket
        assert cp2.price == Decimal('10.00')
        assert cp2.item == self.food

        # Make sure cart expires
        cp1.expires = now() - datetime.timedelta(minutes=120)
        cp1.save()
        cp2.expires = now() - datetime.timedelta(minutes=120)
        cp2.save()

        # Verify price is kept if cart expires and order is sent
        with scopes_disabled():
            _perform_order(self.event, self._manual_payment(), [cp1.pk, cp2.pk], 'admin@example.org', 'en', None, {}, 'web')
            op1 = OrderPosition.objects.get(is_bundled=False)
            op2 = OrderPosition.objects.get(is_bundled=True)
        assert op1.price == Decimal('17.37')
        assert op1.item == self.ticket
        assert op1.tax_rate == Decimal('19.00')
        assert op2.price == Decimal('10.00')
        assert op2.item == self.food
        assert op2.tax_rate == Decimal('7.00')
