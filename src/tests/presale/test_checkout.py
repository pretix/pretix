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
import hashlib
import json
import os
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from bs4 import BeautifulSoup
from django.conf import settings
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.signing import dumps
from django.test import TestCase
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django_countries.fields import Country
from django_scopes import scopes_disabled
from freezegun import freeze_time

from pretix.base.decimal import round_decimal
from pretix.base.models import (
    CartPosition, Discount, Event, Invoice, InvoiceAddress, Item, ItemCategory,
    Order, OrderPayment, OrderPosition, Organizer, Question, QuestionAnswer,
    Quota, SeatingPlan, Voucher,
)
from pretix.base.models.customers import CustomerSSOProvider
from pretix.base.models.items import (
    ItemAddOn, ItemBundle, ItemVariation, SubEventItem, SubEventItemVariation,
)
from pretix.base.services.orders import OrderError, _perform_order
from pretix.base.services.tax import VATIDFinalError, VATIDTemporaryError
from pretix.testutils.scope import classscope
from pretix.testutils.sessions import get_cart_session_key


class BaseCheckoutTestCase:
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(now().year + 1, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.stripe,pretix.plugins.banktransfer',
            live=True
        )
        self.tr19 = self.event.tax_rules.create(rate=19)
        self.category = ItemCategory.objects.create(event=self.event, name="Everything", position=0)
        self.quota_tickets = Quota.objects.create(event=self.event, name='Tickets', size=5)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          category=self.category, default_price=23, admission=True,
                                          personalized=True, tax_rule=self.tr19)
        self.quota_tickets.items.add(self.ticket)
        self.event.settings.set('timezone', 'UTC')
        self.event.settings.set('attendee_names_asked', False)
        self.event.settings.set('payment_banktransfer__enabled', True)

        self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.session_key = get_cart_session_key(self.client, self.event)
        self._set_session('email', 'admin@localhost')

        self.workshopcat = ItemCategory.objects.create(name="Workshops", is_addon=True, event=self.event)
        self.workshopquota = Quota.objects.create(event=self.event, name='Workshop 1', size=5)
        self.workshop1 = Item.objects.create(event=self.event, name='Workshop 1',
                                             category=self.workshopcat, default_price=Decimal('12.00'))
        self.workshop2 = Item.objects.create(event=self.event, name='Workshop 2',
                                             category=self.workshopcat, default_price=Decimal('12.00'))
        self.workshop2a = ItemVariation.objects.create(item=self.workshop2, value='A')
        self.workshop2b = ItemVariation.objects.create(item=self.workshop2, value='B')
        self.workshopquota.items.add(self.workshop1)
        self.workshopquota.items.add(self.workshop2)
        self.workshopquota.variations.add(self.workshop2a)
        self.workshopquota.variations.add(self.workshop2b)

    def _set_session(self, key, value):
        session = self.client.session
        session['carts'][get_cart_session_key(self.client, self.event)][key] = value
        session.save()

    def _set_payment(self):
        self._set_session('payments', [{
            "id": "test1",
            "provider": "banktransfer",
            "max_value": None,
            "min_value": None,
            "multi_use_supported": False,
            "info_data": {},
        }])

    def _manual_payment(self):
        return [{
            "id": "test1",
            "provider": "manual",
            "max_value": None,
            "min_value": None,
            "multi_use_supported": False,
            "info_data": {},
        }]


class CheckoutTestCase(BaseCheckoutTestCase, TestCase):

    def _enable_reverse_charge(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )
        self._set_session('invoice_address', ia.pk)
        return ia

    def _enable_country_specific_taxing(self):
        self.tr19.custom_rules = json.dumps([
            {'country': 'EU', 'address_type': 'individual', 'action': 'vat', 'rate': '20.00'},
            {'country': 'US', 'address_type': 'individual', 'action': 'vat', 'rate': '10.00'},
        ])
        self.tr19.save()
        with scopes_disabled():
            ia = InvoiceAddress.objects.create(
                country=Country('AT'),
            )
        self._set_session('invoice_address', ia.pk)
        return ia

    def test_empty_cart(self):
        response = self.client.get('/%s/%s/checkout/start' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_reverse_charge(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = 'AT123456'
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1234',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == round_decimal(Decimal('23.00') / Decimal('1.19'))

        with scopes_disabled():
            ia = InvoiceAddress.objects.get(pk=self.client.session['carts'][self.session_key].get('invoice_address'))
        assert ia.vat_id_validated

    def test_reverse_charge_enable_then_disable(self):
        self.test_reverse_charge()

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = 'AT123456'
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'individual',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1234',
                'city': 'Here',
                'country': 'AT',
                'vat_id': '',
                'email': 'admin@localhost'
            }, follow=True)

        with scopes_disabled():
            cr = CartPosition.objects.get(cart_id=self.session_key)
            assert cr.price == Decimal('23.00')

            ia = InvoiceAddress.objects.get(pk=self.client.session['carts'][self.session_key].get('invoice_address'))
            assert not ia.vat_id_validated

    def test_reverse_charge_invalid_vatid(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            def raiser(*args, **kwargs):
                raise VATIDFinalError('final')

            mock_validate.side_effect = raiser
            resp = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1234',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)
            assert 'alert-danger' in resp.content.decode()

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.00')

    def test_reverse_charge_vatid_non_eu(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('NO')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = ('AU', 'AU123456', 'Foo')
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '3000',
                'city': 'Here',
                'country': 'AU',
                'state': 'QLD',
                'vat_id': 'AU123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == round_decimal(Decimal('23.00') / Decimal('1.19'))

        with scopes_disabled():
            ia = InvoiceAddress.objects.get(pk=self.client.session['carts'][self.session_key].get('invoice_address'))
        assert not ia.vat_id_validated

    def test_reverse_charge_vatid_same_country(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('AT')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = 'AT123456'
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1234',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.00')

        with scopes_disabled():
            ia = InvoiceAddress.objects.get(pk=self.client.session['carts'][self.session_key].get('invoice_address'))
        assert ia.vat_id_validated

    def test_reverse_charge_vatid_check_invalid_country(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        resp = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'company': 'Foo',
            'name': 'Bar',
            'street': 'Baz',
            'zipcode': '1234',
            'city': 'Here',
            'country': 'FR',
            'vat_id': 'AT123456',
            'email': 'admin@localhost'
        }, follow=True)
        assert 'alert-danger' in resp.content.decode()

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.00')

    def test_reverse_charge_vatid_check_unavailable(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            def raiser(*args, **kwargs):
                raise VATIDTemporaryError('temp')

            mock_validate.side_effect = raiser
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1234',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.00')

        with scopes_disabled():
            ia = InvoiceAddress.objects.get(pk=self.client.session['carts'][self.session_key].get('invoice_address'))
        assert not ia.vat_id_validated

    def test_reverse_charge_keep_gross(self):
        self.tr19.eu_reverse_charge = True
        self.tr19.keep_gross_if_rate_changes = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = 'AT123456'
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1234',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.00')
        assert cr1.tax_rate == Decimal('0.00')
        assert cr1.tax_value == Decimal('0.00')

        with scopes_disabled():
            ia = InvoiceAddress.objects.get(pk=self.client.session['carts'][self.session_key].get('invoice_address'))
        assert ia.vat_id_validated

    def test_custom_tax_rules(self):
        self.tr19.custom_rules = json.dumps([
            {'country': 'AT', 'address_type': 'business_vat_id', 'action': 'reverse'},
            {'country': 'ZZ', 'address_type': '', 'action': 'vat'},
        ])
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = 'AT123456'
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1234',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('19.33')

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = ('DE', 'DE123456', 'Foo')
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '12345',
                'city': 'Here',
                'country': 'DE',
                'vat_id': 'DE123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.00')

    def test_custom_tax_rules_blocked_on_fee(self):
        self.tr7 = self.event.tax_rules.create(rate=7)
        self.tr7.custom_rules = json.dumps([
            {'country': 'AT', 'address_type': 'business_vat_id', 'action': 'reverse'},
            {'country': 'ZZ', 'address_type': '', 'action': 'block'},
        ])
        self.tr7.save()
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('payment_banktransfer__fee_percent', 20)
        self.event.settings.set('payment_banktransfer__fee_reverse_calc', False)
        self.event.settings.set('tax_rate_default', self.tr7)
        self.event.settings.invoice_address_vatid = True

        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'company': 'Foo',
            'name': 'Bar',
            'street': 'Baz',
            'zipcode': '12345',
            'city': 'Here',
            'country': 'DE',
            'email': 'admin@localhost'
        }, follow=True)

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = 'AT123456'
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1234',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)

        self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)

        r = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(r.content.decode(), "lxml")
        assert doc.select(".alert-danger")
        assert "not available in the selected country" in doc.select(".alert-danger")[0].text

    def test_custom_tax_rules_blocked(self):
        self.tr19.custom_rules = json.dumps([
            {'country': 'AT', 'address_type': 'business_vat_id', 'action': 'reverse'},
            {'country': 'ZZ', 'address_type': '', 'action': 'block'},
        ])
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        r = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'company': 'Foo',
            'name': 'Bar',
            'street': 'Baz',
            'zipcode': '12345',
            'city': 'Here',
            'country': 'DE',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(r.content.decode(), "lxml")
        assert doc.select(".alert-danger")

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.00')

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = 'AT123456'
            r = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1234',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)
        doc = BeautifulSoup(r.content.decode(), "lxml")
        assert not doc.select(".alert-danger")

        cr1.refresh_from_db()
        assert cr1.price == Decimal('19.33')

    def test_custom_tax_rules_require_approval(self):
        self.tr19.custom_rules = json.dumps([
            {'country': 'AT', 'address_type': 'business_vat_id', 'action': 'reverse'},
            {'country': 'ZZ', 'address_type': '', 'action': 'require_approval'},
        ])
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'company': 'Foo',
            'name': 'Bar',
            'street': 'Baz',
            'zipcode': '12345',
            'city': 'Here',
            'country': 'DE',
            'email': 'admin@localhost'
        }, follow=True)

        self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        with scopes_disabled():
            assert not CartPosition.objects.filter(pk=cr1.pk).exists()
            o = Order.objects.last()
            assert o.require_approval
            assert o.positions.first().tax_rate == Decimal('19.00')

    def _test_country_taxing(self):
        self._enable_country_specific_taxing()

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = 'AT123456'
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'individual',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1234',
                'city': 'Here',
                'country': 'AT',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.20')
        assert cr1.tax_rate == Decimal('20.00')
        assert cr1.tax_value == Decimal('3.87')
        return cr1

    def test_country_taxing(self):
        cr1 = self._test_country_taxing()

        self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)

        self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        with scopes_disabled():
            assert not CartPosition.objects.filter(pk=cr1.pk).exists()
            o = Order.objects.last()
            pos = o.positions.get()
            assert pos.price == Decimal('23.20')
            assert pos.tax_rate == Decimal('20.00')
            assert pos.tax_value == Decimal('3.87')
            t = o.transactions.get()
            assert t.price == Decimal('23.20')
            assert t.tax_rate == Decimal('20.00')
            assert t.tax_value == Decimal('3.87')

    def test_country_taxing_free_price_and_voucher(self):
        self._enable_country_specific_taxing()

        self.ticket.free_price = True
        self.ticket.save()

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, listed_price=23, price_after_voucher=23, custom_price_input=23, custom_price_input_is_net=False,
                expires=now() + timedelta(minutes=10),
                voucher=self.event.vouchers.create()
            )

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = 'AT123456'
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'individual',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1234',
                'city': 'Here',
                'country': 'AT',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('23.20')

        self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)

        self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        with scopes_disabled():
            assert not CartPosition.objects.filter(pk=cr1.pk).exists()
            o = Order.objects.last()
            assert o.positions.get().price == Decimal('23.20')

    def test_country_taxing_switch(self):
        self._test_country_taxing()

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = 'AT123456'
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'individual',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '99501',
                'city': 'Here',
                'country': 'US',
                'state': 'CA',
                'email': 'admin@localhost'
            }, follow=True)

        with scopes_disabled():
            cr = CartPosition.objects.get(cart_id=self.session_key)
            assert cr.price == Decimal('21.26')

    def test_free_price_net_price_reverse_charge_keep_gross_but_enforce_min(self):
        # This is an end-to-end test of a very confusing case in which the event is set to
        # "show net prices" but the tax rate is set to "keep gross if rate changes" in
        # combination of free prices.
        # This means the user will be greeted with a display price of "23 EUR + VAT". If they
        # then adjust the price to pay more, e.g. "24 EUR", it will be interpreted as a net
        # value (since the event is set to shown net values). The cart position is therefore
        # created with a gross price of 28.56 EUR. Then, the user enters their invoice address, which
        # triggers reverse charge. The tax is now removed, and the price would be reverted to "24.00 + 0%",
        # however that is now lower than the minimum price of "27.37 incl VAT", so the price is raised to 27.37.
        self.event.settings.display_net_prices = True
        self.ticket.free_price = True
        self.ticket.save()
        self.tr19.eu_reverse_charge = True
        self.tr19.keep_gross_if_rate_changes = True
        self.tr19.price_includes_tax = False
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'price_%d' % self.ticket.id: '24.00',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        with scopes_disabled():
            cr1 = CartPosition.objects.get()
            assert cr1.listed_price == Decimal('23.00')
            assert cr1.custom_price_input == Decimal('24.00')
            assert cr1.custom_price_input_is_net
            assert cr1.price == Decimal('28.56')
            assert cr1.tax_rate == Decimal('19.00')

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = 'AT123456'
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1345',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('27.37')
        assert cr1.tax_rate == Decimal('0.00')

        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            op = OrderPosition.objects.get()
            self.assertEqual(op.price, Decimal('27.37'))
            self.assertEqual(op.tax_value, Decimal('0.00'))
            self.assertEqual(op.tax_rate, Decimal('0.00'))

    def test_free_price_net_price_reverse_charge_keep_gross(self):
        # This is the slightly happier case of the previous test in which the event is set to
        # "show net prices" but the tax rate is set to "keep gross if rate changes" in
        # combination of free prices.
        # This means the user will be greeted with a display price of "23 EUR + VAT". If they
        # then adjust the price to pay more, e.g. "40 EUR", it will be interpreted as a net
        # value (since the event is set to shown net values). The cart position is therefore
        # created with a gross price of 47.60 EUR. Then, the user enters their invoice address, which
        # triggers reverse charge. The tax is now removed, and the price is reverted to "40.00 + 0%"
        # since that was the user's original intent.
        self.event.settings.display_net_prices = True
        self.ticket.free_price = True
        self.ticket.save()
        self.tr19.eu_reverse_charge = True
        self.tr19.keep_gross_if_rate_changes = True
        self.tr19.price_includes_tax = False
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        self.event.settings.invoice_address_vatid = True

        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'price_%d' % self.ticket.id: '40.00',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        with scopes_disabled():
            cr1 = CartPosition.objects.get()
            assert cr1.listed_price == Decimal('23.00')
            assert cr1.custom_price_input == Decimal('40.00')
            assert cr1.custom_price_input_is_net
            assert cr1.price == Decimal('47.60')
            assert cr1.tax_rate == Decimal('19.00')

        with mock.patch('pretix.base.services.tax._validate_vat_id_EU') as mock_validate:
            mock_validate.return_value = 'AT123456'
            self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
                'is_business': 'business',
                'company': 'Foo',
                'name': 'Bar',
                'street': 'Baz',
                'zipcode': '1234',
                'city': 'Here',
                'country': 'AT',
                'vat_id': 'AT123456',
                'email': 'admin@localhost'
            }, follow=True)

        cr1.refresh_from_db()
        assert cr1.price == Decimal('40.00')
        assert cr1.tax_rate == Decimal('0.00')

        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            op = OrderPosition.objects.get()
            self.assertEqual(op.price, Decimal('40.00'))
            self.assertEqual(op.tax_value, Decimal('0.00'))
            self.assertEqual(op.tax_rate, Decimal('0.00'))

    def test_question_file_upload(self):
        with scopes_disabled():
            q1 = Question.objects.create(
                event=self.event, question='Student ID', type=Question.TYPE_FILE,
                required=False
            )
            self.ticket.questions.add(q1)
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")

        self.assertEqual(len(doc.select('input[name="%s-question_%s"]' % (cr1.id, q1.id))), 1)

        f = SimpleUploadedFile("testfile.txt", b"file_content")
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-question_%s' % (cr1.id, q1.id): f,
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
            a = cr1.answers.get(question=q1)
            assert a.file
            assert a.file.read() == b"file_content"
            assert os.path.exists(os.path.join(settings.MEDIA_ROOT, a.file.name))

        # Delete
        self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-question_%s-clear' % (cr1.id, q1.id): 'on',
            'email': 'admin@localhost'
        }, follow=True)
        with scopes_disabled():
            assert not cr1.answers.exists()
        assert not os.path.exists(os.path.join(settings.MEDIA_ROOT, a.file.name))

    def test_phone_required(self):
        self.event.settings.set('order_phone_asked', True)
        self.event.settings.set('order_phone_required', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="phone_1"]')), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'email': 'admin@localhost',
        }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'email': 'admin@localhost',
            'phone_0': '+49',
            'phone_1': '0622199999',  # yeah the 0 is wrong but users don't know that so it should work fine
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer',
        }, follow=True)
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            o = Order.objects.last()
            assert o.phone == '+49622199999'

    def test_attendee_email_required(self):
        self.event.settings.set('attendee_emails_asked', True)
        self.event.settings.set('attendee_emails_required', True)
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="%s-attendee_email"]' % cr1.id)), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-attendee_email' % cr1.id: '',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-attendee_email' % cr1.id: 'foo@localhost',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.attendee_email, 'foo@localhost')

    def test_attendee_company_required(self):
        self.event.settings.set('attendee_company_asked', True)
        self.event.settings.set('attendee_company_required', True)
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="%s-company"]' % cr1.id)), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-company' % cr1.id: '',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-company' % cr1.id: 'foobar',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.company, 'foobar')

    def test_attendee_address_required(self):
        self.event.settings.set('attendee_addresses_asked', True)
        self.event.settings.set('attendee_addresses_required', True)
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('textarea[name="%s-street"]' % cr1.id)), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-street' % cr1.id: '',
            '%s-zipcode' % cr1.id: '',
            '%s-city' % cr1.id: '',
            '%s-country' % cr1.id: '',
            '%s-state' % cr1.id: '',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-street' % cr1.id: 'Musterstrasse',
            '%s-zipcode' % cr1.id: '12345',
            '%s-city' % cr1.id: 'Musterstadt',
            '%s-country' % cr1.id: 'DE',
            '%s-state' % cr1.id: '',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.street, 'Musterstrasse')
        self.assertEqual(cr1.zipcode, '12345')
        self.assertEqual(cr1.city, 'Musterstadt')
        self.assertEqual(cr1.country, 'DE')

    def test_attendee_name_required(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', True)
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_0"]' % cr1.id)), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-attendee_name_parts_0' % cr1.id: '',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-attendee_name_parts_0' % cr1.id: 'Peter',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.attendee_name, 'Peter')

    def test_attendee_name_not_required_if_ticket_unpersonalized(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', True)
        self.ticket.personalized = False
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_0"]' % cr1.id)), 0)

        # Accepted request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.attendee_name, None)

    def test_attendee_name_scheme(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', True)
        self.event.settings.set('name_scheme', 'salutation_title_given_family')
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('select[name="%s-attendee_name_parts_0"]' % cr1.id)), 1)
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_1"]' % cr1.id)), 1)
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_2"]' % cr1.id)), 1)
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_3"]' % cr1.id)), 1)
        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-attendee_name_parts_0' % cr1.id: 'Mr',
            '%s-attendee_name_parts_1' % cr1.id: '',
            '%s-attendee_name_parts_2' % cr1.id: 'John',
            '%s-attendee_name_parts_3' % cr1.id: 'Doe',
            'email': 'admin@localhost'
        })
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.attendee_name, 'John Doe')
        self.assertEqual(cr1.attendee_name_parts, {
            'salutation': 'Mr',
            'title': '',
            'given_name': 'John',
            'family_name': 'Doe',
            "_scheme": "salutation_title_given_family"
        })

    def test_attendee_name_optional(self):
        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', False)
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="%s-attendee_name_parts_0"]' % cr1.id)), 1)

        # Not all fields filled out, expect success
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-attendee_name_parts_0' % cr1.id: '',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
        assert not cr1.attendee_name

    def test_invoice_address_required(self):
        self.event.settings.invoice_address_asked = True
        self.event.settings.invoice_address_required = True
        self.event.settings.invoice_address_not_asked_free = True
        self.event.settings.set('name_scheme', 'title_given_middle_family')

        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="city"]')), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'city': 'Here',
            'country': 'DE',
            'vat_id': 'DE123456',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'company': 'Foo',
            'name_parts_0': 'Mr',
            'name_parts_1': 'John',
            'name_parts_2': '',
            'name_parts_3': 'Kennedy',
            'street': 'Baz',
            'zipcode': '12345',
            'city': 'Here',
            'country': 'DE',
            'vat_id': 'DE123456',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        with scopes_disabled():
            ia = InvoiceAddress.objects.last()
        assert ia.name_parts == {
            'title': 'Mr',
            'given_name': 'John',
            'middle_name': '',
            'family_name': 'Kennedy',
            "_scheme": "title_given_middle_family"
        }
        assert ia.name_cached == 'Mr John Kennedy'

    def test_invoice_address_validated(self):
        self.event.settings.invoice_address_asked = True
        self.event.settings.invoice_address_required = True
        self.event.settings.invoice_address_not_asked_free = True
        self.event.settings.set('name_scheme', 'title_given_middle_family')

        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="city"]')), 1)

        # Not all required fields filled out correctly, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'company': 'Foo',
            'name_parts_0': 'Mr',
            'name_parts_1': 'John',
            'name_parts_2': '',
            'name_parts_3': 'Kennedy',
            'street': 'Baz',
            'zipcode': '123456',
            'city': 'Here',
            'country': 'DE',
            'vat_id': 'DE123456',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'company': 'Foo',
            'name_parts_0': 'Mr',
            'name_parts_1': 'John',
            'name_parts_2': '',
            'name_parts_3': 'Kennedy',
            'street': 'Baz',
            'zipcode': '12345',
            'city': 'Here',
            'country': 'DE',
            'vat_id': 'DE123456',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_invoice_address_hidden_for_free(self):
        self.event.settings.invoice_address_asked = True
        self.event.settings.invoice_address_required = True
        self.event.settings.invoice_address_not_asked_free = True
        self.event.settings.set('name_scheme', 'title_given_middle_family')

        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=0, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="city"]')), 0)

        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_invoice_address_optional(self):
        self.event.settings.invoice_address_asked = True
        self.event.settings.invoice_address_required = False

        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="city"]')), 1)

        # Partial address is not allowed
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'country': 'DE',
            'city': 'Musterstadt',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # No address works
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'is_business': 'business',
            'country': 'DE',
            'vat_id': 'DE123456',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_invoice_name_required(self):
        self.event.settings.invoice_address_asked = False
        self.event.settings.invoice_name_required = True

        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="name_parts_0"]')), 1)
        self.assertEqual(len(doc.select('input[name="street"]')), 0)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'name_parts_0': 'Raphael',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_payment(self):
        # TODO: Test for correct payment method fees
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 2)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_payment_max_value(self):
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__total_max', Decimal('42.00'))
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 2)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 1)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(".alert-danger")

    def test_payment_hidden(self):
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('payment_banktransfer__hidden', True)
        self.event.settings.set('payment_banktransfer__hidden_seed', get_random_string(32))
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 1)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(".alert-danger")

        self.client.get('/%s/%s/unlock/%s/' % (
            self.orga.slug, self.event.slug,
            hashlib.sha256(
                (self.event.settings.payment_banktransfer__hidden_seed + self.event.slug).encode()
            ).hexdigest(),
        ), follow=True)

        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 2)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert not doc.select(".alert-danger")

    def test_payment_min_value(self):
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__total_min', Decimal('42.00'))
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 1)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(".alert-danger")

    def test_payment_country_ignored_without_invoice_address_required(self):
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__restricted_countries', ['DE', 'AT'])
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('invoice_address_required', False)
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('CH')
        )
        self._set_session('invoice_address', ia.pk)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 2)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert not doc.select(".alert-danger")

    def test_payment_country_allowed(self):
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__restricted_countries', ['DE', 'AT'])
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('invoice_address_required', True)
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('DE'), name_parts={'full_name': 'Foo', "_scheme": "full"}, name_cached='Foo', street='Foo'
        )
        self._set_session('invoice_address', ia.pk)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 2)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert not doc.select(".alert-danger")

    def test_payment_country_blocked(self):
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__restricted_countries', ['DE', 'AT'])
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('invoice_address_required', True)
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('CH'), name_parts={'full_name': 'Foo', "_scheme": "full"}, name_cached='Foo', street='Foo'
        )
        self._set_session('invoice_address', ia.pk)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 1)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(".alert-danger")

    def test_giftcard_partial(self):
        gc = self.orga.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=20, acceptor=self.orga)
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 3)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert '€20.00' in response.content.decode()
        assert '3.00' in response.content.decode()
        assert 'alert-success' in response.content.decode()

        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert '€20.00' in response.content.decode()
        assert '3.00' in response.content.decode()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            o = Order.objects.last()
            p1 = o.payments.get(provider='giftcard')
            p2 = o.payments.get(provider='banktransfer')
            assert p1.amount == Decimal('20.00')
            assert p1.state == OrderPayment.PAYMENT_STATE_CONFIRMED
            assert p2.amount == Decimal('3.00')
            assert p2.state == OrderPayment.PAYMENT_STATE_CREATED

    def test_giftcard_full_with_multiple(self):
        gc = self.orga.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=20, acceptor=self.orga)
        gc2 = self.orga.issued_gift_cards.create(currency="EUR")
        gc2.transactions.create(value=20, acceptor=self.orga)
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 3)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert '€20.00' in response.content.decode()
        assert '€3.00' in response.content.decode()
        assert 'alert-success' in response.content.decode()

        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc2.secret
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            o = Order.objects.last()
            [p1, p2] = o.payments.all()
            assert p1.amount == Decimal('20.00')
            assert p1.state == OrderPayment.PAYMENT_STATE_CONFIRMED
            assert p2.amount == Decimal('3.00')
            assert p2.state == OrderPayment.PAYMENT_STATE_CONFIRMED

    def test_giftcard_full(self):
        gc = self.orga.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=30, acceptor=self.orga)
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 3)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            o = Order.objects.last()
            p1 = o.payments.get(provider='giftcard')
            assert p1.amount == Decimal('23.00')
            assert p1.state == OrderPayment.PAYMENT_STATE_CONFIRMED

    def test_giftcard_racecondition(self):
        gc = self.orga.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=20, acceptor=self.orga)
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 3)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert '€20.00' in response.content.decode()
        assert '3.00' in response.content.decode()
        assert 'alert-success' in response.content.decode()

        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert '€20.00' in response.content.decode()
        assert '3.00' in response.content.decode()

        gc.transactions.create(value=-2, acceptor=self.orga)

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert "used in the meantime" in doc.select('.alert-warning')[0].text
        with scopes_disabled():
            o = Order.objects.last()
            assert o.status == Order.STATUS_PENDING
            p1 = o.payments.get(provider='giftcard')
            p2 = o.payments.get(provider='banktransfer')
            assert p1.amount == Decimal('20.00')
            assert p1.state == OrderPayment.PAYMENT_STATE_FAILED
            assert p2.amount == Decimal('3.00')
            assert p2.state == OrderPayment.PAYMENT_STATE_CANCELED

    def test_giftcard_expired(self):
        gc = self.orga.issued_gift_cards.create(currency="EUR", expires=now() - timedelta(days=1))
        gc.transactions.create(value=20, acceptor=self.orga)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        assert 'This gift card is no longer valid.' in response.content.decode()

    def test_giftcard_invalid_currency(self):
        gc = self.orga.issued_gift_cards.create(currency="USD")
        gc.transactions.create(value=20, acceptor=self.orga)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        assert 'This gift card does not support this currency.' in response.content.decode()

    def test_giftcard_invalid_organizer(self):
        self.orga.issued_gift_cards.create(currency="EUR")
        orga2 = Organizer.objects.create(slug="foo2", name="foo2")
        gc = orga2.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=20, acceptor=self.orga)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        assert 'This gift card is not known.' in response.content.decode()

    def test_giftcard_cross_organizer(self):
        self.orga.issued_gift_cards.create(currency="EUR")
        orga2 = Organizer.objects.create(slug="foo2", name="foo2")
        gc = orga2.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=23, acceptor=orga2)
        self.orga.gift_card_issuer_acceptance.create(issuer=orga2)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            o = Order.objects.last()
            p = o.payments.get(provider='giftcard')
            assert p.amount == Decimal('23.00')
            gc.refresh_from_db()
            assert gc.issuer == orga2
            assert gc.transactions.last().acceptor == self.orga

    def test_giftcard_cross_organizer_inactive(self):
        self.orga.issued_gift_cards.create(currency="EUR")
        orga2 = Organizer.objects.create(slug="foo2", name="foo2")
        gc = orga2.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=23, acceptor=orga2)
        self.orga.gift_card_issuer_acceptance.create(issuer=orga2, active=False)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        assert 'This gift card is not known.' in response.content.decode()

    def test_giftcard_in_test_mode(self):
        gc = self.orga.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=20, acceptor=self.orga)
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.testmode = True
        self.event.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        assert 'Only test gift cards can be used in test mode.' in response.content.decode()

    def test_giftcard_not_in_test_mode(self):
        gc = self.orga.issued_gift_cards.create(currency="EUR", testmode=True)
        gc.transactions.create(value=20, acceptor=self.orga)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        assert 'This gift card can only be used in test mode.' in response.content.decode()

    def test_giftcard_empty(self):
        gc = self.orga.issued_gift_cards.create(currency="EUR")
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        assert 'All credit on this gift card has been used.' in response.content.decode()

    def test_giftcard_twice(self):
        gc = self.orga.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=20, acceptor=self.orga)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        assert 'This gift card is already used for your payment.' in response.content.decode()

    def test_giftcard_swap(self):
        gc = self.orga.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=20, acceptor=self.orga)
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.ticket.issue_giftcard = True
        self.ticket.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        assert 'You cannot pay with gift cards when buying a gift card.' in response.content.decode()

    def test_giftcard_like_method_with_min_value(self):
        gc = self.orga.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=20, acceptor=self.orga)
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        payments = [{
            "id": "test1",
            "provider": "giftcard",
            "max_value": None,
            "min_value": "25.00",
            "multi_use_supported": True,
            "info_data": {
                'gift_card': gc.pk
            },
        }]
        self._set_session('payments', payments)
        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'at least €25.00' in response.content.decode()

        # perform_order should never be called, but let's see what happens if it does…
        with scopes_disabled():
            with pytest.raises(OrderError, match='The selected payment methods do not cover the total balance.'):
                _perform_order(self.event, payments, [cp1.pk], 'admin@example.org', 'en', None, {}, 'web')

    def test_payment_fee_for_giftcard_payment_paid_with_same_card(self):
        # Our built-in gift card payment does not actually support setting a payment fee, but we still want to
        # test the core behavior in case a gift-card plugin does
        gc = self.orga.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=27, acceptor=self.orga)
        self.event.settings.set('payment_giftcard__fee_percent', 10)
        self.event.settings.set('payment_giftcard__fee_reverse_calc', False)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 2)

        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        fees = response.context_data['cart']['fees']
        assert len(fees) == 1
        assert fees[0].value == Decimal('2.30')
        assert response.context_data['cart']['total'] == Decimal('25.30')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            o = Order.objects.last()
            p1 = o.payments.get()
            assert p1.amount == Decimal('25.30')
            assert p1.state == OrderPayment.PAYMENT_STATE_CONFIRMED
            assert p1.fee.value == Decimal("2.30")
            assert o.total == Decimal("25.30")

    def test_payment_fee_for_giftcard_payment_paid_with_other_method(self):
        # Our built-in gift card payment does not actually support setting a payment fee, but we still want to
        # test the core behavior in case a gift-card plugin does
        gc = self.orga.issued_gift_cards.create(currency="EUR")
        gc.transactions.create(value=23, acceptor=self.orga)
        self.event.settings.set('payment_banktransfer__enabled', True)
        self.event.settings.set('payment_banktransfer__fee_percent', 20)
        self.event.settings.set('payment_banktransfer__fee_reverse_calc', False)
        self.event.settings.set('payment_giftcard__fee_percent', 10)
        self.event.settings.set('payment_giftcard__fee_reverse_calc', False)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select('input[name="payment"]')), 2)

        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'giftcard',
            'giftcard': gc.secret
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        fees = response.context_data['cart']['fees']
        assert len(fees) == 1
        assert fees[0].value == Decimal('2.30')
        assert response.context_data['cart']['total'] == Decimal('25.30')

        response = self.client.post('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), {
            'payment': 'banktransfer',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        fees = response.context_data['cart']['fees']
        assert len(fees) == 2
        assert fees[0].value == Decimal('2.30')
        assert fees[1].value == Decimal('0.46')
        assert response.context_data['cart']['total'] == Decimal('25.76')

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            o = Order.objects.last()
            p1 = o.payments.get(provider='giftcard')
            p2 = o.payments.get(provider='banktransfer')
            assert p1.amount == Decimal('23.00')
            assert p1.state == OrderPayment.PAYMENT_STATE_CONFIRMED
            assert p2.amount == Decimal('2.76')
            assert p2.state == OrderPayment.PAYMENT_STATE_CREATED
            assert p1.fee.value == Decimal("2.30")
            assert p2.fee.value == Decimal("0.46")
            assert o.total == Decimal("25.76")

    def test_premature_confirm(self):
        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        self._set_payment()

        self.event.settings.set('attendee_names_asked', True)
        self.event.settings.set('attendee_names_required', True)

        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1.attendee_name_parts = {"full_name": 'Peter', "_scheme": "full"}
        cr1.save()
        with scopes_disabled():
            q1 = Question.objects.create(
                event=self.event, question='Age', type=Question.TYPE_NUMBER,
                required=True
            )
        self.ticket.questions.add(q1)

        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        q1.required = False
        q1.save()
        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertEqual(response.status_code, 200)

        self._set_session('email', 'invalid')
        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_subevent(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now())
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.ticket)
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10), subevent=se
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.first().subevent, se)

    def test_require_approval_no_payment_step(self):
        self.event.settings.invoice_generate = 'True'
        self.ticket.require_approval = True
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=42, listed_price=42, price_after_voucher=42, expires=now() + timedelta(minutes=10)
            )

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(Order.objects.first().status, Order.STATUS_PENDING)
            self.assertTrue(Order.objects.first().require_approval)
            self.assertEqual(OrderPosition.objects.count(), 1)
            self.assertEqual(Invoice.objects.count(), 0)

    def test_require_approval_no_payment_step_free(self):
        self.ticket.require_approval = True
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=0, listed_price=0, price_after_voucher=0, expires=now() + timedelta(minutes=10)
            )

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        with scopes_disabled():
            self.assertEqual(len(doc.select(".thank-you")), 1)
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(Order.objects.first().status, Order.STATUS_PENDING)
            self.assertTrue(Order.objects.first().require_approval)
            self.assertEqual(OrderPosition.objects.count(), 1)

    def test_require_approval_in_addon_to_free(self):
        with scopes_disabled():
            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1,
                                     price_included=True)
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=0, listed_price=0, price_after_voucher=0, expires=now() - timedelta(minutes=10)
            )
        self.ticket.default_price = 0
        self.ticket.save()
        self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)

        self.workshop1.require_approval = True
        self.workshop1.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.workshop1,
                price=0, listed_price=0, price_after_voucher=0, expires=now() - timedelta(minutes=10),
                addon_to=cp1
            )
        self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cp1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(Order.objects.first().status, Order.STATUS_PENDING)
            self.assertTrue(Order.objects.first().require_approval)
            self.assertEqual(OrderPayment.objects.count(), 0)
            self.assertEqual(OrderPosition.objects.count(), 2)

    def test_free_price(self):
        self.ticket.free_price = True
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=42, listed_price=42, price_after_voucher=42, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        with scopes_disabled():
            self.assertEqual(len(doc.select(".thank-you")), 1)
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.first().price, 42)

    def test_free_order(self):
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=0, listed_price=0, price_after_voucher=0, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.first().price, 0)
            self.assertEqual(Order.objects.first().status, Order.STATUS_PAID)

    def test_free_order_require_approval(self):
        self.ticket.require_approval = True
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=0, listed_price=0, price_after_voucher=0, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.first().price, 0)
            self.assertEqual(Order.objects.first().status, Order.STATUS_PENDING)
            self.assertEqual(Order.objects.first().require_approval, True)

    def test_confirm_in_time(self):
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        with scopes_disabled():
            self.assertEqual(len(doc.select(".thank-you")), 1)
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)
            self.assertEqual(Order.objects.first().status, Order.STATUS_PENDING)

    def test_subevent_confirm_expired_available(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se = self.event.subevents.create(name='Foo', date_from=now())
            se2 = self.event.subevents.create(name='Foo', date_from=now())
            self.quota_tickets.size = 0
            self.quota_tickets.subevent = se2
            self.quota_tickets.save()
            q2 = se.quotas.create(event=self.event, size=1, name='Bar')
            q2.items.add(self.ticket)
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), subevent=se
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)

    def test_confirm_expired_available(self):
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)

    def test_subevent_confirm_price_changed(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now())
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.ticket)
            SubEventItem.objects.create(subevent=se, item=self.ticket, price=24)
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), subevent=se
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
            self.assertEqual(cr1.price, 24)

    def test_subevent_disabled(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now())
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.ticket)
            SubEventItem.objects.create(subevent=se, item=self.ticket, price=24, disabled=True)
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), subevent=se
            )
        self._set_payment()

        self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        with scopes_disabled():
            assert not CartPosition.objects.filter(id=cr1.id).exists()

    def test_subevent_variation_disabled(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now())
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.workshop2)
            q.variations.add(self.workshop2b)
            SubEventItemVariation.objects.create(subevent=se, variation=self.workshop2b, price=24, disabled=True)
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.workshop2, variation=self.workshop2b,
                price=23, expires=now() - timedelta(minutes=10), subevent=se
            )
        self._set_payment()

        self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        with scopes_disabled():
            assert not CartPosition.objects.filter(id=cr1.id).exists()

    def test_subevent_availability(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now())
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.ticket)
            SubEventItem.objects.create(subevent=se, item=self.ticket, price=24, available_until=now() - timedelta(days=1))
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), subevent=se
            )
        self._set_payment()

        self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        with scopes_disabled():
            assert not CartPosition.objects.filter(id=cr1.id).exists()

    def test_subevent_variation_availability(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now())
            q = se.quotas.create(name="foo", size=None, event=self.event)
            q.items.add(self.workshop2)
            q.variations.add(self.workshop2b)
            SubEventItemVariation.objects.create(subevent=se, variation=self.workshop2b, price=24, available_from=now() + timedelta(days=1))
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.workshop2, variation=self.workshop2b,
                price=23, expires=now() - timedelta(minutes=10), subevent=se
            )
        self._set_payment()

        self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        with scopes_disabled():
            assert not CartPosition.objects.filter(id=cr1.id).exists()

    def test_addon_price_included(self):
        with scopes_disabled():
            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1,
                                     price_included=True)
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.workshop1,
                price=0, expires=now() - timedelta(minutes=10),
                addon_to=cp1
            )

        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertEqual(OrderPosition.objects.filter(item=self.workshop1).last().price, 0)

    def test_addon_price_included_in_voucher(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('0.00'), event=self.event, price_mode='set',
                                       valid_until=now() + timedelta(days=2), all_addons_included=True)
            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1,
                                     price_included=False)
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=0, expires=now() - timedelta(minutes=10), voucher=v
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.workshop1,
                price=0, expires=now() - timedelta(minutes=10),
                addon_to=cp1
            )

        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertEqual(OrderPosition.objects.filter(item=self.workshop1).last().price, 0)

    def test_confirm_price_changed_reverse_charge(self):
        self._enable_reverse_charge()
        self.ticket.default_price = 24
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
            self.assertEqual(cr1.price, round_decimal(Decimal('24.00') / Decimal('1.19')))

    def test_confirm_price_changed_reverse_charge_keep_gross(self):
        self._enable_reverse_charge()
        self.tr19.keep_gross_if_rate_changes = True
        self.tr19.save()
        self.ticket.default_price = 24
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(cr1.price, Decimal('24.00'))

    def test_confirm_price_not_changed_reverse_charge_keep_gross(self):
        self._enable_reverse_charge()
        self.tr19.keep_gross_if_rate_changes = True
        self.tr19.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            op = OrderPosition.objects.get()
            self.assertEqual(op.price, Decimal('23.00'))
            self.assertEqual(op.tax_value, Decimal('0.00'))
            self.assertEqual(op.tax_rate, Decimal('0.00'))

    def test_confirm_price_changed(self):
        self.ticket.default_price = 24
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
            self.assertEqual(cr1.price, 24)

    def test_confirm_free_price_increased(self):
        self.ticket.default_price = 24
        self.ticket.free_price = True
        self.ticket.save()

        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                listed_price=23, price_after_voucher=23, custom_price_input=23, price=23,
                expires=now() - timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
            self.assertEqual(cr1.price, 24)

    @freeze_time("2023-01-18 03:00:00+01:00")
    def test_validity_requested_start_date(self):
        self.ticket.validity_mode = Item.VALIDITY_MODE_DYNAMIC
        self.ticket.validity_dynamic_duration_days = 1
        self.ticket.validity_dynamic_start_choice = True
        self.ticket.validity_dynamic_start_choice_day_limit = 30
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=42, listed_price=42, price_after_voucher=42, expires=now() + timedelta(minutes=10)
            )

        # Date too far in the future, expected to fail
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-requested_valid_from' % cr1.id: '2024-01-20',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-requested_valid_from' % cr1.id: '2023-01-20',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1.refresh_from_db()
        assert cr1.requested_valid_from.isoformat() == '2023-01-20T00:00:00+00:00'

        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        with scopes_disabled():
            self.assertEqual(len(doc.select(".thank-you")), 1)
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)
            op = OrderPosition.objects.get()
            assert op.valid_from.isoformat() == '2023-01-20T00:00:00+00:00'
            assert op.valid_until.isoformat() == '2023-01-20T23:59:59+00:00'

    @freeze_time("2023-01-18 03:00:00+01:00")
    def test_validity_requested_start_date_and_time(self):
        self.ticket.validity_mode = Item.VALIDITY_MODE_DYNAMIC
        self.ticket.validity_dynamic_duration_hours = 2
        self.ticket.validity_dynamic_start_choice = True
        self.ticket.validity_dynamic_start_choice_day_limit = 30
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=42, listed_price=42, price_after_voucher=42, expires=now() + timedelta(minutes=10)
            )

        # Date too far in the future, expected to fail
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-requested_valid_from_0' % cr1.id: '2024-01-20',
            '%s-requested_valid_from_1' % cr1.id: '11:00:00',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-requested_valid_from_0' % cr1.id: '2023-01-20',
            '%s-requested_valid_from_1' % cr1.id: '11:00:00',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        cr1.refresh_from_db()
        assert cr1.requested_valid_from.isoformat() == '2023-01-20T11:00:00+00:00'

        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        with scopes_disabled():
            self.assertEqual(len(doc.select(".thank-you")), 1)
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)
            op = OrderPosition.objects.get()
            assert op.valid_from.isoformat() == '2023-01-20T11:00:00+00:00'
            assert op.valid_until.isoformat() == '2023-01-20T13:00:00+00:00'

    def test_voucher(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                       valid_until=now() + timedelta(days=2))
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() + timedelta(minutes=10), voucher=v
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.first().voucher, v)
            self.assertEqual(Voucher.objects.get(pk=v.pk).redeemed, 1)

    def test_voucher_required(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                       valid_until=now() + timedelta(days=2))
            self.ticket.require_voucher = True
            self.ticket.save()
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() + timedelta(minutes=10), voucher=v
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertEqual(Voucher.objects.get(pk=v.pk).redeemed, 1)

    def test_voucher_required_but_missing(self):
        self.ticket.require_voucher = True
        self.ticket.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        assert doc.select(".alert-danger")

    def test_voucher_price_changed(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                       valid_until=now() + timedelta(days=2))
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=13, expires=now() - timedelta(minutes=10), voucher=v
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
            self.assertEqual(cr1.price, Decimal('12.00'))

    def test_voucher_redeemed(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                       valid_until=now() + timedelta(days=2), redeemed=1)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertIn("has already been", doc.select(".alert-danger")[0].text)

    def test_voucher_multiuse_redeemed(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                       valid_until=now() + timedelta(days=2), max_usages=3, redeemed=3)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertIn("has already been", doc.select(".alert-danger")[0].text)

    def test_voucher_multiuse_partially(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                       valid_until=now() + timedelta(days=2), max_usages=3, redeemed=2)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertIn("has already been", doc.select(".alert-danger")[0].text)
        with scopes_disabled():
            assert CartPosition.objects.filter(cart_id=self.session_key).count() == 1

    def test_voucher_multiuse_ok(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                       valid_until=now() + timedelta(days=2), max_usages=3, redeemed=1)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        with scopes_disabled():
            doc = BeautifulSoup(response.content.decode(), "lxml")
            self.assertEqual(len(doc.select(".thank-you")), 1)
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 2)
            v.refresh_from_db()
            assert v.redeemed == 3

    def test_voucher_multiuse_in_other_cart_expired(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event,
                                       price_mode='set',
                                       valid_until=now() + timedelta(days=2), max_usages=3, redeemed=1)
            CartPosition.objects.create(
                event=self.event, cart_id='other', item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 2)
            v.refresh_from_db()
            assert v.redeemed == 3

    def test_voucher_multiuse_in_other_cart(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                       valid_until=now() + timedelta(days=2), max_usages=3, redeemed=1)
            CartPosition.objects.create(
                event=self.event, cart_id='other', item=self.ticket,
                price=12, expires=now() + timedelta(minutes=10), voucher=v
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertIn("has already been", doc.select(".alert-danger")[0].text)
        with scopes_disabled():
            assert CartPosition.objects.filter(cart_id=self.session_key).count() == 1

    def test_voucher_min_usages(self):
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), price_mode='set', event=self.event,
                                       valid_until=now() + timedelta(days=2), max_usages=10, redeemed=1,
                                       min_usages=3)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() + timedelta(minutes=10), voucher=v
            )
        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertIn("at least 2", doc.select(".alert-danger")[0].text)

        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() + timedelta(minutes=10), voucher=v
            )
        self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug))  # required for session['shown_total']
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 2)

    def test_voucher_ignore_quota(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                       valid_until=now() + timedelta(days=2), allow_ignore_quota=True)
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)

    def test_voucher_block_quota(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='set',
                                       valid_until=now() + timedelta(days=2), block_quota=True)
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key).count(), 0)
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )

        self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)

    def test_voucher_block_quota_other_quota_full(self):
        with scopes_disabled():
            self.quota_tickets.size = 0
            self.quota_tickets.save()
            q2 = self.event.quotas.create(name='Testquota', size=0)
            q2.items.add(self.ticket)
            v = Voucher.objects.create(quota=self.quota_tickets, value=Decimal('12.00'), event=self.event,
                                       valid_until=now() + timedelta(days=2), block_quota=True)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=12, expires=now() - timedelta(minutes=10), voucher=v
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertTrue(doc.select(".alert-danger"))
        with scopes_disabled():
            self.assertFalse(Order.objects.exists())

    def test_voucher_double(self):
        self.quota_tickets.size = 2
        self.quota_tickets.save()
        with scopes_disabled():
            v = Voucher.objects.create(item=self.ticket, event=self.event,
                                       valid_until=now() + timedelta(days=2), block_quota=True)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10), voucher=v
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10), voucher=v
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, voucher=v).count(), 1)
            self.assertEqual(len(doc.select(".alert-danger")), 1)
            self.assertFalse(Order.objects.exists())

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, voucher=v).exists())
            self.assertEqual(len(doc.select(".thank-you")), 1)
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)

    def test_discount_success(self):
        with scopes_disabled():
            Discount.objects.create(event=self.event, condition_min_count=2, benefit_discount_matching_percent=20)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                listed_price=23, price_after_voucher=23, price=18.4, expires=now() - timedelta(minutes=10),
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                listed_price=23, price_after_voucher=23, price=18.4, expires=now() - timedelta(minutes=10),
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key).exists())
            self.assertEqual(len(doc.select(".thank-you")), 1)
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 2)
            self.assertEqual(OrderPosition.objects.filter(price=18.4).count(), 2)

    def test_discount_changed(self):
        with scopes_disabled():
            Discount.objects.create(event=self.event, condition_min_count=2, benefit_discount_matching_percent=20)
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                listed_price=23, price_after_voucher=23, price=23, expires=now() - timedelta(minutes=10),
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                listed_price=23, price_after_voucher=23, price=23, expires=now() - timedelta(minutes=10),
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
            self.assertEqual(cr1.price, Decimal('18.40'))

    def test_max_per_item_failed(self):
        self.quota_tickets.size = 3
        self.quota_tickets.save()
        self.ticket.max_per_order = 1
        self.ticket.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10),
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10),
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key).count(), 1)
            self.assertEqual(len(doc.select(".alert-danger")), 1)
            self.assertFalse(Order.objects.exists())

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        with scopes_disabled():
            self.assertEqual(len(doc.select(".thank-you")), 1)
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(OrderPosition.objects.count(), 1)

    def test_subevent_confirm_expired_partial(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now())
            se2 = self.event.subevents.create(name='Foo', date_from=now())
            self.quota_tickets.size = 10
            self.quota_tickets.subevent = se2
            self.quota_tickets.save()
            q2 = se.quotas.create(event=self.event, size=1, name='Bar')
            q2.items.add(self.ticket)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), subevent=se
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), subevent=se
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), subevent=se2
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key).count(), 2)

    def test_confirm_expired_partial(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key).count(), 1)

    def test_confirm_event_over(self):
        self.event.date_to = now() - datetime.timedelta(days=1)
        self.event.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)

    def test_confirm_presale_over(self):
        self.event.presale_end = now() - datetime.timedelta(days=1)
        self.event.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)

    def test_confirm_payment_period_over(self):
        self.event.settings.payment_term_last = (now() - datetime.timedelta(days=1)).date().isoformat()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)

    def test_confirm_require_voucher(self):
        self.ticket.require_voucher = True
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_require_hide_without_voucher(self):
        self.ticket.require_voucher = True
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_no_longer_available(self):
        self.ticket.available_until = now() - timedelta(days=1)
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_inactive(self):
        self.ticket.active = False
        self.ticket.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_expired_unavailable(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_completely_unavailable(self):
        self.quota_tickets.items.remove(self.ticket)
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_expired_with_blocking_voucher_unavailable(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = Voucher.objects.create(quota=self.quota_tickets, event=self.event, block_quota=True)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket, voucher=v,
                price=23, expires=now() - timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)

    def test_confirm_expired_with_non_blocking_voucher_unavailable(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = Voucher.objects.create(quota=self.quota_tickets, event=self.event)
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket, voucher=v,
                price=23, expires=now() - timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())

    def test_confirm_not_expired_with_blocking_voucher_unavailable(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = Voucher.objects.create(quota=self.quota_tickets, event=self.event, block_quota=True)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket, voucher=v,
                price=23, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)

    def test_confirm_not_expired_with_non_blocking_voucher_unavailable(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = Voucher.objects.create(quota=self.quota_tickets, event=self.event)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket, voucher=v,
                price=23, expires=now() + timedelta(minutes=10)
            )
        self._set_payment()

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)

    def test_addons_as_first_step(self):
        with scopes_disabled():
            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )

        response = self.client.get('/%s/%s/checkout/start' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_set_addons_item_and_variation(self):
        with scopes_disabled():
            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat)
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )
            cp2 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )

        response = self.client.post('/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug), {
            'cp_{}_item_{}'.format(cp1.pk, self.workshop1.pk): '1',
            'cp_{}_variation_{}_{}'.format(cp2.pk, self.workshop2.pk, self.workshop2a.pk): '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        with scopes_disabled():
            assert cp1.addons.first().item == self.workshop1
            assert cp2.addons.first().item == self.workshop2
            assert cp2.addons.first().variation == self.workshop2a

    def test_set_addon_multi(self):
        with scopes_disabled():
            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, multi_allowed=True, max_count=2)
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )

        response = self.client.post('/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug), {
            'cp_{}_item_{}'.format(cp1.pk, self.workshop1.pk): '2',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        with scopes_disabled():
            assert cp1.addons.count() == 2
            assert cp1.addons.first().item == self.workshop1
            assert cp1.addons.last().item == self.workshop1

    def test_set_addon_free_price(self):
        self.event.settings.locales = ['de']
        self.event.settings.locale = 'de'

        with scopes_disabled():
            self.workshop1.free_price = True
            self.workshop1.save()
            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat)
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )

        response = self.client.post('/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug), {
            'cp_{}_item_{}'.format(cp1.pk, self.workshop1.pk): '1',
            'cp_{}_item_{}_price'.format(cp1.pk, self.workshop1.pk): '999,99',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        with scopes_disabled():
            assert cp1.addons.count() == 1
            assert cp1.addons.first().item == self.workshop1
            assert cp1.addons.first().price == Decimal('999.99')

    def test_set_addons_required(self):
        with scopes_disabled():
            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )

        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug))
        self.assertRedirects(response, '/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        response = self.client.get('/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug))
        assert 'Workshop 1' in response.content.decode()
        assert '€12.00' in response.content.decode()

    def test_set_addons_included(self):
        with scopes_disabled():
            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1,
                                     price_included=True)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )

        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'Workshop 1' in response.content.decode()
        assert '€12.00' not in response.content.decode()

    def test_set_addons_hide_sold_out(self):
        with scopes_disabled():
            self.workshopquota.size = 0
            self.workshopquota.save()

            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )

        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'Workshop 1' in response.content.decode()
        self.event.settings.hide_sold_out = True

        response = self.client.get('/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug), follow=True)
        assert 'Workshop 1' not in response.content.decode()

    def test_set_addons_hidden_if_available(self):
        with scopes_disabled():
            self.workshopquota2 = Quota.objects.create(event=self.event, name='Workshop 1', size=5)
            self.workshopquota2.items.add(self.workshop2)
            self.workshopquota2.variations.add(self.workshop2a)
            self.workshop2.hidden_if_available = self.workshopquota
            self.workshop2.save()

            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10)
            )

        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'Workshop 1' in response.content.decode()
        assert 'Workshop 2' not in response.content.decode()

        self.workshopquota.size = 0
        self.workshopquota.save()

        response = self.client.get('/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug), follow=True)
        assert 'Workshop 1' in response.content.decode()
        assert 'Workshop 2' in response.content.decode()

    def test_set_addons_subevent(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se = self.event.subevents.create(name='Foo', date_from=now())
            self.workshopquota.size = 1
            self.workshopquota.subevent = se
            self.workshopquota.save()
            SubEventItem.objects.create(subevent=se, item=self.workshop1, price=42)

            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), subevent=se
            )

        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert '42.00' in response.content.decode()

    def test_set_addons_subevent_net_prices(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.settings.display_net_prices = True
            self.event.save()
            se = self.event.subevents.create(name='Foo', date_from=now())
            self.workshopquota.size = 1
            self.workshopquota.subevent = se
            self.workshopquota.save()
            self.workshop1.tax_rule = self.event.tax_rules.get_or_create(rate=Decimal('19.00'), name="VAT")[0]
            self.workshop1.save()
            self.workshop2.tax_rule = self.event.tax_rules.get_or_create(rate=Decimal('19.00'), name="VAT")[0]
            self.workshop2.save()
            SubEventItem.objects.create(subevent=se, item=self.workshop1, price=42)

            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1)
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() - timedelta(minutes=10), subevent=se
            )

        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/addons/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert '35.29' in response.content.decode()
        assert '10.08' in response.content.decode()

    def test_confirm_subevent_presale_not_yet(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.settings.display_net_prices = True
            self.event.save()
            se = self.event.subevents.create(name='Foo', date_from=now(), presale_start=now() + datetime.timedelta(days=1))
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10), subevent=se
            )

        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        assert 'booking period for one of the events in your cart has not yet started.' in response.content.decode()
        with scopes_disabled():
            assert not CartPosition.objects.filter(cart_id=self.session_key).exists()

    def test_confirm_subevent_presale_over(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.settings.display_net_prices = True
            self.event.save()
            se = self.event.subevents.create(name='Foo', date_from=now(), presale_end=now() - datetime.timedelta(days=1))
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10), subevent=se
            )

        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        assert 'booking period for one of the events in your cart has ended.' in response.content.decode()
        with scopes_disabled():
            assert not CartPosition.objects.filter(cart_id=self.session_key).exists()

    def test_confirm_subevent_payment_period_over(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.settings.display_net_prices = True
            self.event.save()
            self.event.settings.payment_term_last = 'RELDATE/1/23:59:59/date_from/'
            se = self.event.subevents.create(name='Foo', date_from=now())
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10), subevent=se
            )

        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select(".alert-danger")), 1)
        assert 'booking period for one of the events in your cart has ended.' in response.content.decode()
        with scopes_disabled():
            assert not CartPosition.objects.filter(cart_id=self.session_key).exists()

    def test_confirm_subevent_ignore_series_dates(self):
        self.event.has_subevents = True
        self.event.date_to = now() - datetime.timedelta(days=1)
        self.event.save()
        with scopes_disabled():
            se = self.event.subevents.create(name='Foo', date_from=now(), presale_end=now() + datetime.timedelta(days=1))
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10), subevent=se
            )

        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)

    def test_create_testmode_order_in_testmode(self):
        self.event.testmode = True
        self.event.save()
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        self._set_payment()
        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        assert "test mode" in response.content.decode()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            assert Order.objects.last().testmode
            assert Order.objects.last().code[1] == "0"

    def test_do_not_create_testmode_order_without_testmode(self):
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )

        self._set_payment()
        response = self.client.get('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        assert "test mode" not in response.content.decode()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            assert not Order.objects.last().testmode
            assert "0" not in Order.objects.last().code

    def test_receive_order_confirmation_and_paid_mail(self):
        with scopes_disabled():
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
            djmail.outbox = []
            oid = _perform_order(self.event, self._manual_payment(), [cp1.pk], 'admin@example.org', 'en', None, {}, 'web')
            assert len(djmail.outbox) == 1
            o = Order.objects.get(pk=oid['order_id'])
            o.payments.first().confirm()
            assert len(djmail.outbox) == 2

    def test_order_confirmation_and_paid_mail_not_send_on_disabled_sales_channel(self):
        with scopes_disabled():
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
            djmail.outbox = []
            self.event.settings.mail_sales_channel_placed_paid = []
            oid = _perform_order(self.event, self._manual_payment(), [cp1.pk], 'admin@example.org', 'en', None, {}, 'web')
            assert len(djmail.outbox) == 0
            o = Order.objects.get(pk=oid['order_id'])
            o.payments.first().confirm()
            assert len(djmail.outbox) == 0

    def test_locale_region_not_saved(self):
        self.event.settings.origin = 'US'
        self.event.settings.locales = ['de']
        self.event.settings.locale = 'de'
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=0, listed_price=0, price_after_voucher=0, expires=now() + timedelta(minutes=10)
            )

        self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        with scopes_disabled():
            self.assertEqual(Order.objects.first().locale, 'de')

    def test_variation_require_approval(self):
        self.workshop2a.require_approval = True
        self.workshop2a.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.workshop2, variation=self.workshop2a,
                price=0, listed_price=0, price_after_voucher=0, expires=now() + timedelta(minutes=10)
            )

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(Order.objects.first().status, Order.STATUS_PENDING)
            self.assertTrue(Order.objects.first().require_approval)
            self.assertEqual(OrderPosition.objects.count(), 1)
            self.assertEqual(Invoice.objects.count(), 0)

    def test_item_with_variations_require_approval(self):
        self.workshop2.require_approval = True
        self.workshop2.save()
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.workshop2, variation=self.workshop2a,
                price=0, listed_price=0, price_after_voucher=0, expires=now() + timedelta(minutes=10)
            )

        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertFalse(CartPosition.objects.filter(id=cr1.id).exists())
            self.assertEqual(Order.objects.count(), 1)
            self.assertEqual(Order.objects.first().status, Order.STATUS_PENDING)
            self.assertTrue(Order.objects.first().require_approval)
            self.assertEqual(OrderPosition.objects.count(), 1)
            self.assertEqual(Invoice.objects.count(), 0)


class QuestionsTestCase(BaseCheckoutTestCase, TestCase):

    def test_timezone(self):
        """ Test basic timezone change handling by date and time questions """
        with scopes_disabled():
            q1 = Question.objects.create(
                event=self.event, question='When did you wake up today?', type=Question.TYPE_TIME,
                required=True
            )
            q2 = Question.objects.create(
                event=self.event, question='When was your last haircut?', type=Question.TYPE_DATE,
                required=True
            )
            q3 = Question.objects.create(
                event=self.event, question='When are you going to arrive?', type=Question.TYPE_DATETIME,
                required=True
            )
            self.ticket.questions.add(q1)
            self.ticket.questions.add(q2)
            self.ticket.questions.add(q3)
            cr = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-question_%s' % (cr.id, q1.id): '06:30',
            '%s-question_%s' % (cr.id, q2.id): '2005-12-31',
            '%s-question_%s_0' % (cr.id, q3.id): '2018-01-01',
            '%s-question_%s_1' % (cr.id, q3.id): '5:23',
            'email': 'admin@localhost',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), target_status_code=200)
        self.event.settings.set('timezone', 'US/Central')
        with scopes_disabled():
            o1 = QuestionAnswer.objects.get(question=q1)
            o2 = QuestionAnswer.objects.get(question=q2)
            o3 = QuestionAnswer.objects.get(question=q3)
            order = Order.objects.create(event=self.event, status=Order.STATUS_PAID,
                                         expires=now() + timedelta(days=3),
                                         total=4)
            op = OrderPosition.objects.create(order=order, item=self.ticket, price=42)
            o1.cartposition, o2.cartposition, o3.cartposition = None, None, None
            o1.orderposition, o2.orderposition, o3.orderposition = op, op, op
            # only time and date answers should be unaffected by timezone change
            self.assertEqual(str(o1), '06:30')
            self.assertEqual(str(o2), '2005-12-31')
            o3date, o3time = str(o3).split(' ')
            self.assertEqual(o3date, '2017-12-31')
            self.assertEqual(o3time, '23:23')

    def test_addon_questions(self):
        with scopes_disabled():
            q1 = Question.objects.create(
                event=self.event, question='Age', type=Question.TYPE_NUMBER,
                required=True
            )
            q1.items.add(self.ticket)
            q1.items.add(self.workshop1)
            ItemAddOn.objects.create(base_item=self.ticket, addon_category=self.workshopcat, min_count=1,
                                     price_included=True)
            cp1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
            cp1.answers.create(question=q1, answer='12')
            cp2 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.workshop1, addon_to=cp1,
                price=0, expires=now() + timedelta(minutes=10)
            )
            cp2.answers.create(question=q1, answer='12')

        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)
        with scopes_disabled():
            self.assertEqual(OrderPosition.objects.filter(item=self.ticket).first().answers.first().answer, '12')
            self.assertEqual(OrderPosition.objects.filter(item=self.workshop1).first().answers.first().answer, '12')

    def test_questions(self):
        with scopes_disabled():
            q1 = Question.objects.create(
                event=self.event, question='Age', type=Question.TYPE_NUMBER,
                required=True
            )
            q2 = Question.objects.create(
                event=self.event, question='How have you heard from us?', type=Question.TYPE_STRING,
                required=False
            )
            self.ticket.questions.add(q1)
            self.ticket.questions.add(q2)
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
            cr2 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")

        self.assertEqual(len(doc.select('input[name="%s-question_%s"]' % (cr1.id, q1.id))), 1)
        self.assertEqual(len(doc.select('input[name="%s-question_%s"]' % (cr2.id, q1.id))), 1)
        self.assertEqual(len(doc.select('input[name="%s-question_%s"]' % (cr1.id, q2.id))), 1)
        self.assertEqual(len(doc.select('input[name="%s-question_%s"]' % (cr2.id, q2.id))), 1)

        # Not all required fields filled out, expect failure
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-question_%s' % (cr1.id, q1.id): '42',
            '%s-question_%s' % (cr2.id, q1.id): '',
            '%s-question_%s' % (cr1.id, q2.id): 'Internet',
            '%s-question_%s' % (cr2.id, q2.id): '',
            'email': 'admin@localhost'
        }, follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertGreaterEqual(len(doc.select('.has-error')), 1)

        # Corrected request
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            '%s-question_%s' % (cr1.id, q1.id): '42',
            '%s-question_%s' % (cr2.id, q1.id): '0',
            '%s-question_%s' % (cr1.id, q2.id): 'Internet',
            '%s-question_%s' % (cr2.id, q2.id): '',
            'email': 'admin@localhost'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        with scopes_disabled():
            cr1 = CartPosition.objects.get(id=cr1.id)
            cr2 = CartPosition.objects.get(id=cr2.id)
            self.assertEqual(cr1.answers.filter(question=q1).count(), 1)
            self.assertEqual(cr2.answers.filter(question=q1).count(), 1)
            self.assertEqual(cr1.answers.filter(question=q2).count(), 1)
            self.assertFalse(cr2.answers.filter(question=q2).exists())

    def _test_question_input(self, data, should_fail, try_with_initial=True):
        with scopes_disabled():
            cr1 = CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
        pl = {
            ('%s-question_%s' % (cr1.id, k.id)): v for k, v in data.items() if v != 'False'
        }
        pl['email'] = 'admin@localhost'
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), pl, follow=True)
        if should_fail:
            doc = BeautifulSoup(response.content.decode(), "lxml")
            assert doc.select('.has-error')
            assert doc.select('.alert-danger')
        else:
            self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                                 target_status_code=200)
            with scopes_disabled():
                if try_with_initial:
                    cr1.answers.all().delete()

        if try_with_initial:
            with scopes_disabled():
                for k, v in data.items():
                    a = cr1.answers.create(question=k, answer=str(v))
                    if k.type in ('M', 'C'):
                        a.options.add(*k.options.filter(identifier__in=(v if isinstance(v, list) else [v])))

        response = self.client.get('/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug), follow=True)
        if should_fail:
            self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                                 target_status_code=200)
            doc = BeautifulSoup(response.content.decode(), "lxml")
            assert doc.select('.alert-warning')
        else:
            assert response.status_code == 200
            doc = BeautifulSoup(response.content.decode(), "lxml")
            assert not doc.select('.alert-warning')

    @scopes_disabled()
    def _setup_dependency_questions(self):
        self.q1 = self.event.questions.create(
            event=self.event, question='What industry are you in?', type=Question.TYPE_CHOICE,
            required=True
        )
        self.q1.options.create(answer='Tech', identifier='TECH')
        self.q1.options.create(answer='Health', identifier='HEALTH')
        self.q1.options.create(answer='IT', identifier='IT')

        self.q2a = self.event.questions.create(
            event=self.event, question='What is your occupation?', type=Question.TYPE_CHOICE_MULTIPLE,
            required=False, dependency_question=self.q1, dependency_values=['TECH', 'IT']
        )
        self.q2a.options.create(answer='Software developer', identifier='DEV')
        self.q2a.options.create(answer='System administrator', identifier='ADMIN')

        self.q2b = self.event.questions.create(
            event=self.event, question='What is your occupation?', type=Question.TYPE_CHOICE_MULTIPLE,
            required=True, dependency_question=self.q1, dependency_values=['HEALTH']
        )
        self.q2b.options.create(answer='Doctor', identifier='DOC')
        self.q2b.options.create(answer='Nurse', identifier='NURSE')

        self.q3 = self.event.questions.create(
            event=self.event, question='Do you like Python?', type=Question.TYPE_BOOLEAN,
            required=False, dependency_question=self.q2a, dependency_values=['DEV']
        )
        self.q4a = self.event.questions.create(
            event=self.event, question='Why?', type=Question.TYPE_TEXT,
            required=True, dependency_question=self.q3, dependency_values=['True']
        )
        self.q4b = self.event.questions.create(
            event=self.event, question='Why not?', type=Question.TYPE_TEXT,
            required=True, dependency_question=self.q3, dependency_values=['False']
        )

        self.ticket.questions.add(self.q1)
        self.ticket.questions.add(self.q2a)
        self.ticket.questions.add(self.q2b)
        self.ticket.questions.add(self.q3)
        self.ticket.questions.add(self.q4a)
        self.ticket.questions.add(self.q4b)

    def test_question_dependencies_first_path(self):
        self._setup_dependency_questions()
        self._test_question_input({
            self.q1: 'HEALTH',
            self.q2b: 'NURSE'
        }, should_fail=False)

    def test_question_dependencies_sidepath_ignored(self):
        self._setup_dependency_questions()
        self._test_question_input({
            self.q1: 'HEALTH',
            self.q2b: 'NURSE',
            self.q2a: 'DEV',
            self.q3: 'True',
        }, should_fail=False)

    def test_question_dependencies_first_path_required(self):
        self._setup_dependency_questions()
        self._test_question_input({
            self.q1: 'HEALTH',
        }, should_fail=True)

    def test_question_dependencies_second_path(self):
        self._setup_dependency_questions()
        self._test_question_input({
            self.q1: 'TECH',
            self.q2a: 'DEV',
            self.q3: 'True',
            self.q4a: 'No curly braces!'
        }, should_fail=False)

    def test_question_dependencies_second_path_alterative(self):
        self._setup_dependency_questions()
        self._test_question_input({
            self.q1: 'IT',
            self.q2a: 'DEV',
            self.q3: 'True',
            self.q4a: 'No curly braces!'
        }, should_fail=False)

    def test_question_dependencies_subitem_required(self):
        self._setup_dependency_questions()
        self._test_question_input({
            self.q1: 'HEALTH',
        }, should_fail=True)

    def test_question_dependencies_subsubitem_required(self):
        self._setup_dependency_questions()
        self._test_question_input({
            self.q1: 'TECH',
            self.q2a: 'DEV',
            self.q3: 'True',
        }, should_fail=True)

    def test_question_dependencies_subsubitem_required_alternative(self):
        self._setup_dependency_questions()
        self._test_question_input({
            self.q1: 'IT',
            self.q2a: 'DEV',
            self.q3: 'True',
        }, should_fail=True)

    def test_question_dependencies_hidden_question_not_saved_to_db(self):
        self._setup_dependency_questions()
        self._test_question_input({
            self.q1: 'IT',
            self.q2a: 'ADMIN',
            self.q3: 'False',
            self.q4b: 'No curly braces!'
        }, should_fail=False, try_with_initial=False)

        with scopes_disabled():
            # We don't want QuestionAnswer objects to be created for questions we did not ask,
            # especially not for boolean answers set to false.
            assert QuestionAnswer.objects.filter(question=self.q1).exists()
            assert QuestionAnswer.objects.filter(question=self.q2a).exists()
            assert not QuestionAnswer.objects.filter(question=self.q3).exists()
            assert not QuestionAnswer.objects.filter(question=self.q4b).exists()

    def test_question_dependencies_parent_not_required(self):
        self._setup_dependency_questions()
        self._test_question_input({
            self.q1: 'TECH',
        }, should_fail=False)

    def test_question_dependencies_conditional_require_bool(self):
        self._setup_dependency_questions()
        self._test_question_input({
            self.q1: 'TECH',
            self.q2a: 'DEV',
            self.q3: 'False',
            self.q4b: 'No curly braces!'
        }, should_fail=False)

    def test_question_dependencies_conditional_require_bool_fail(self):
        self._setup_dependency_questions()
        self._test_question_input({
            self.q1: 'TECH',
            self.q2a: 'DEV',
            self.q3: 'False',
        }, should_fail=True)


class CheckoutBundleTest(BaseCheckoutTestCase, TestCase):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.trans = Item.objects.create(event=self.event, name='Public Transport Ticket',
                                         default_price=2.50)
        self.transquota = Quota.objects.create(event=self.event, name='Transport', size=5)
        self.transquota.items.add(self.trans)
        self.bundle1 = ItemBundle.objects.create(
            base_item=self.ticket,
            bundled_item=self.trans,
            designated_price=1.5,
            count=1
        )
        self.cp1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=21.5, listed_price=23, price_after_voucher=23, expires=now() + timedelta(minutes=10)
        )
        self.bundled1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=self.cp1,
            price=1.5, listed_price=1.5, price_after_voucher=1.5, expires=now() + timedelta(minutes=10), is_bundled=True
        )

    @classscope(attr='orga')
    def test_simple_bundle(self):
        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 23 - 1.5
        assert cp.addons.count() == 1
        a = cp.addons.get()
        assert a.item == self.trans
        assert a.price == 1.5

    @classscope(attr='orga')
    def test_simple_bundle_with_variation(self):
        v = self.trans.variations.create(value="foo", default_price=4)
        self.transquota.variations.add(v)
        self.bundle1.bundled_variation = v
        self.bundle1.save()
        self.bundled1.variation = v
        self.bundled1.save()

        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 23 - 1.5
        assert cp.addons.count() == 1
        a = cp.addons.get()
        assert a.item == self.trans
        assert a.variation == v
        assert a.price == 1.5

    @classscope(attr='orga')
    def test_bundle_with_count(self):
        self.cp1.price -= 1.5
        self.cp1.save()
        bundled2 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=self.cp1,
            price=1.5, expires=now() + timedelta(minutes=10), is_bundled=True
        )
        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk, bundled2.pk], 'admin@example.org', 'en', None, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 23 - 1.5 - 1.5
        assert cp.addons.count() == 2
        a = cp.addons.first()
        assert a.item == self.trans
        assert a.price == 1.5
        a = cp.addons.last()
        assert a.item == self.trans
        assert a.price == 1.5

    @classscope(attr='orga')
    def test_bundle_position_free_price(self):
        self.ticket.free_price = True
        self.ticket.default_price = 1
        self.ticket.save()
        self.cp1.custom_price_input = 20
        self.cp1.listed_price = 1
        self.cp1.price_after_voucher = 1
        self.cp1.line_price = 20 - 1.5
        self.cp1.price = 20 - 1.5
        self.cp1.save()

        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 20 - 1.5
        a = cp.addons.get()
        assert a.item == self.trans
        assert a.price == 1.5

    @classscope(attr='orga')
    def test_bundle_position_free_price_lower_than_designated_price(self):
        self.ticket.free_price = True
        self.ticket.default_price = 1
        self.ticket.save()
        self.cp1.custom_price_input = 1
        self.cp1.listed_price = 1
        self.cp1.price_after_voucher = 1
        self.cp1.line_price = 0
        self.cp1.price = 0
        self.cp1.save()

        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == Decimal('0.00')
        a = cp.addons.get()
        assert a.item == self.trans
        assert a.price == Decimal('1.50')

    @classscope(attr='orga')
    def test_bundle_different_tax_rates(self):
        tr19 = self.event.tax_rules.create(
            name='VAT',
            rate=Decimal('19.00')
        )
        tr7 = self.event.tax_rules.create(
            name='VAT',
            rate=Decimal('7.00'),
            price_includes_tax=True,  # will be ignored
        )
        self.ticket.tax_rule = tr19
        self.ticket.save()
        self.trans.tax_rule = tr7
        self.trans.save()

        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == Decimal('21.50')
        assert cp.tax_rate == Decimal('19.00')
        assert cp.tax_value == Decimal('3.43')
        assert cp.addons.count() == 1
        a = cp.addons.first()
        assert a.item == self.trans
        assert a.price == 1.5
        assert a.tax_rate == Decimal('7.00')
        assert a.tax_value == Decimal('0.10')

    @classscope(attr='orga')
    def test_simple_bundle_with_voucher(self):
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='none',
                                   valid_until=now() + timedelta(days=2))
        self.cp1.voucher = v
        self.cp1.save()
        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 23 - 1.5
        assert cp.addons.count() == 1
        a = cp.addons.get()
        assert a.item == self.trans
        assert a.price == 1.5

    @classscope(attr='orga')
    def test_expired_bundle_with_voucher_bundles_included(self):
        v = Voucher.objects.create(item=self.ticket, value=Decimal('12.00'), event=self.event, price_mode='none',
                                   valid_until=now() + timedelta(days=2), all_bundles_included=True)
        self.cp1.voucher = v
        self.cp1.price = 23
        self.cp1.expires = now() - timedelta(minutes=10)
        self.cp1.save()
        self.bundled1.price = 0
        self.bundled1.expires = now() - timedelta(minutes=10)
        self.bundled1.save()
        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == 23
        assert cp.addons.count() == 1
        a = cp.addons.get()
        assert a.item == self.trans
        assert a.price == 0

    @classscope(attr='orga')
    def test_expired_keep_price(self):
        self.cp1.expires = now() - timedelta(minutes=10)
        self.cp1.save()
        self.bundled1.expires = now() - timedelta(minutes=10)
        self.bundled1.save()

        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        b = cp.addons.first()
        assert cp.price == 21.5
        assert b.price == 1.5

    @classscope(attr='orga')
    def test_expired_designated_price_changed(self):
        self.bundle1.designated_price = Decimal('2.00')
        self.bundle1.save()
        self.cp1.expires = now() - timedelta(minutes=10)
        self.cp1.save()
        self.bundled1.expires = now() - timedelta(minutes=10)
        self.bundled1.save()
        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        b = cp.addons.first()
        assert cp.price == 21
        assert b.price == 2

    @classscope(attr='orga')
    def test_expired_designated_price_changed_beyond_base_price(self):
        self.bundle1.designated_price = Decimal('40.00')
        self.bundle1.save()
        self.cp1.expires = now() - timedelta(minutes=10)
        self.cp1.save()
        self.bundled1.expires = now() - timedelta(minutes=10)
        self.bundled1.save()
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        self.cp1.refresh_from_db()
        self.bundled1.refresh_from_db()
        assert self.cp1.price == 0
        assert self.bundled1.price == 40

    @classscope(attr='orga')
    def test_expired_base_price_changed(self):
        self.ticket.default_price = Decimal('25.00')
        self.ticket.save()
        self.cp1.expires = now() - timedelta(minutes=10)
        self.cp1.save()
        self.bundled1.expires = now() - timedelta(minutes=10)
        self.bundled1.save()
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        self.cp1.refresh_from_db()
        self.bundled1.refresh_from_db()
        assert self.cp1.price == 23.5
        assert self.bundled1.price == 1.5

    @classscope(attr='orga')
    def test_expired_bundled_and_addon(self):
        a = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=self.cp1,
            price=2.5, expires=now() - timedelta(minutes=10), is_bundled=False
        )
        self.cp1.expires = now() - timedelta(minutes=10)
        self.cp1.save()
        self.bundled1.expires = now() - timedelta(minutes=10)
        self.bundled1.save()

        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk, a.pk], 'admin@example.org', 'en', None, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        b = cp.addons.order_by('price').first()
        a = cp.addons.order_by('price').last()
        assert cp.price == 21.5
        assert b.price == 1.5
        assert cp.price == 21.5
        assert b.price == 1.5
        assert a.price == 2.5

    @classscope(attr='orga')
    def test_expired_base_product_sold_out(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        self.cp1.expires = now() - timedelta(minutes=10)
        self.cp1.save()
        self.bundled1.expires = now() - timedelta(minutes=10)
        self.bundled1.save()
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        assert not CartPosition.objects.exists()

    @classscope(attr='orga')
    def test_expired_bundled_product_sold_out(self):
        self.transquota.size = 0
        self.transquota.save()
        self.cp1.expires = now() - timedelta(minutes=10)
        self.cp1.save()
        self.bundled1.expires = now() - timedelta(minutes=10)
        self.bundled1.save()
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', None, {}, 'web')
        assert not CartPosition.objects.exists()

    @classscope(attr='orga')
    def test_expired_bundled_products_sold_out_partially(self):
        self.transquota.size = 1
        self.transquota.save()
        a = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=self.cp1,
            price=1.5, expires=now() - timedelta(minutes=10), is_bundled=True
        )
        self.cp1.price -= 1.5
        self.cp1.expires = now() - timedelta(minutes=10)
        self.cp1.save()
        self.bundled1.expires = now() - timedelta(minutes=10)
        self.bundled1.save()
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk, a.pk], 'admin@example.org', 'en', None, {}, 'web')
        assert not CartPosition.objects.exists()

    @classscope(attr='orga')
    def test_expired_reverse_charge_only_bundled(self):
        tr19 = self.event.tax_rules.create(name='VAT', rate=Decimal('19.00'))
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )
        tr7 = self.event.tax_rules.create(name='VAT', rate=Decimal('7.00'), eu_reverse_charge=True, home_country=Country('DE'))
        self.ticket.tax_rule = tr19
        self.ticket.save()
        self.trans.tax_rule = tr7
        self.trans.save()
        self.cp1.expires = now() - timedelta(minutes=10)
        self.cp1.save()
        self.bundled1.expires = now() - timedelta(minutes=10)
        self.bundled1.price = Decimal('1.40')
        self.bundled1.save()

        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', ia.pk, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == Decimal('21.50')
        assert cp.tax_rate == Decimal('19.00')
        assert cp.tax_value == Decimal('3.43')
        assert cp.addons.count() == 1
        a = cp.addons.first()
        assert a.item == self.trans
        assert a.price == Decimal('1.40')
        assert a.tax_rate == Decimal('0.00')
        assert a.tax_value == Decimal('0.00')

    @classscope(attr='orga')
    def test_expired_reverse_charge_all(self):
        ia = InvoiceAddress.objects.create(
            is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )
        tr19 = self.event.tax_rules.create(name='VAT', rate=Decimal('19.00'), eu_reverse_charge=True, home_country=Country('DE'))
        tr7 = self.event.tax_rules.create(name='VAT', rate=Decimal('7.00'), eu_reverse_charge=True, home_country=Country('DE'))
        self.ticket.tax_rule = tr19
        self.ticket.save()
        self.trans.tax_rule = tr7
        self.trans.save()
        self.cp1.expires = now() - timedelta(minutes=10)
        self.cp1.price = Decimal('18.07')
        self.cp1.save()
        self.bundled1.expires = now() - timedelta(minutes=10)
        self.bundled1.price = Decimal('1.40')
        self.bundled1.save()

        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.bundled1.pk], 'admin@example.org', 'en', ia.pk, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        cp = o.positions.get(addon_to__isnull=True)
        assert cp.item == self.ticket
        assert cp.price == Decimal('18.07')
        assert cp.tax_rate == Decimal('0.00')
        assert cp.tax_value == Decimal('0.00')
        assert cp.addons.count() == 1
        a = cp.addons.first()
        assert a.item == self.trans
        assert a.price == Decimal('1.40')
        assert a.tax_rate == Decimal('0.00')
        assert a.tax_value == Decimal('0.00')

    @classscope(attr='orga')
    def test_addon_and_bundle_through_frontend_stack(self):
        cat = self.event.categories.create(name="addons")
        self.trans.category = cat
        self.trans.save()
        ItemAddOn.objects.create(base_item=self.ticket, addon_category=cat, min_count=1,
                                 price_included=True)
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.trans, addon_to=self.cp1,
            price=0, expires=now() + timedelta(minutes=10), is_bundled=False
        )

        self._set_payment()
        response = self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        doc = BeautifulSoup(response.content.decode(), "lxml")
        self.assertEqual(len(doc.select(".thank-you")), 1)


class CheckoutSeatingTest(BaseCheckoutTestCase, TestCase):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.plan = SeatingPlan.objects.create(
            name="Plan", organizer=self.orga, layout="{}"
        )
        self.event.seat_category_mappings.create(
            layout_category='Stalls', product=self.ticket
        )
        self.seat_a1 = self.event.seats.create(seat_number="A1", product=self.ticket, seat_guid="A1")
        self.seat_a2 = self.event.seats.create(seat_number="A2", product=self.ticket, seat_guid="A2")
        self.seat_a3 = self.event.seats.create(seat_number="A3", product=self.ticket, seat_guid="A3")
        self.cp1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=21.5, listed_price=21.5, price_after_voucher=21.5, expires=now() + timedelta(minutes=10), seat=self.seat_a1
        )

    @scopes_disabled()
    def test_passes(self):
        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk], 'admin@example.org', 'en', None, {}, 'web')
        o = Order.objects.get(pk=oid['order_id'])
        op = o.positions.first()
        assert op.item == self.ticket
        assert op.seat == self.seat_a1

    @scopes_disabled()
    def test_seat_required(self):
        self.cp1.seat = None
        self.cp1.save()
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk], 'admin@example.org', 'en', None, {}, 'web')
        assert not CartPosition.objects.filter(pk=self.cp1.pk).exists()

    @scopes_disabled()
    def test_seat_not_required_if_no_choice(self):
        self.cp1.seat = None
        self.cp1.save()
        self.event.settings.seating_choice = False
        _perform_order(self.event, self._manual_payment(), [self.cp1.pk], 'admin@example.org', 'en', None, {}, 'web')

    @scopes_disabled()
    def test_seat_not_allowed(self):
        self.cp1.item = self.workshop1
        self.cp1.save()
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk], 'admin@example.org', 'en', None, {}, 'web')
        assert not CartPosition.objects.filter(pk=self.cp1.pk).exists()

    @scopes_disabled()
    def test_seat_invalid_product(self):
        self.cp1.item = self.workshop1
        self.cp1.save()
        self.event.seat_category_mappings.create(
            layout_category='Foo', product=self.workshop1
        )
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk], 'admin@example.org', 'en', None, {}, 'web')
        assert not CartPosition.objects.filter(pk=self.cp1.pk).exists()

    @scopes_disabled()
    def test_seat_multiple_times_same_seat(self):
        cp2 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=21.5, expires=now() + timedelta(minutes=10), seat=self.seat_a1
        )
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk, cp2.pk], 'admin@example.org', 'en', None, {}, 'web')
        assert not CartPosition.objects.filter(pk=self.cp1.pk).exists()
        assert not CartPosition.objects.filter(pk=cp2.pk).exists()

    @scopes_disabled()
    def test_seat_blocked(self):
        self.seat_a1.blocked = True
        self.seat_a1.save()
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk], 'admin@example.org', 'en', None, {}, 'web')
        assert not CartPosition.objects.filter(pk=self.cp1.pk).exists()

    @scopes_disabled()
    def test_seat_taken(self):
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key + '_other', item=self.ticket,
            price=21.5, expires=now() + timedelta(minutes=10), seat=self.seat_a1
        )
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk], 'admin@example.org', 'en', None, {}, 'web')
        assert not CartPosition.objects.filter(pk=self.cp1.pk).exists()


class CheckoutVoucherBudgetTest(BaseCheckoutTestCase, TestCase):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.v = Voucher.objects.create(item=self.ticket, value=Decimal('21.50'), event=self.event, price_mode='set',
                                        valid_until=now() + timedelta(days=2), max_usages=999, redeemed=0)
        self.cp1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price_after_voucher=21.5, listed_price=23, price=21.5, expires=now() + timedelta(minutes=10), voucher=self.v
        )
        self.cp2 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price_after_voucher=21.5, listed_price=23, price=21.5, expires=now() + timedelta(minutes=10), voucher=self.v
        )

    @scopes_disabled()
    def test_no_budget(self):
        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.cp2.pk], 'admin@example.org', 'en', None, {},
                             'web')
        o = Order.objects.get(pk=oid['order_id'])
        op = o.positions.first()
        assert op.item == self.ticket
        assert op.voucher_budget_use == Decimal('1.50')

    @scopes_disabled()
    def test_budget_exceeded_for_second_order(self):
        self.v.budget = Decimal('1.50')
        self.v.save()
        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk], 'admin@example.org', 'en', None, {},
                             'web')
        o = Order.objects.get(pk=oid['order_id'])
        op = o.positions.first()
        assert op.item == self.ticket

        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp2.pk], 'admin@example.org', 'en', None, {},
                           'web')
        self.cp2.refresh_from_db()
        assert self.cp2.price == Decimal('23.00')

    @scopes_disabled()
    def test_budget_exceeded_between_positions(self):
        self.v.budget = Decimal('1.50')
        self.v.save()
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.cp2.pk], 'admin@example.org', 'en', None, {},
                           'web')
        self.cp1.refresh_from_db()
        assert self.cp1.price == Decimal('21.50')
        self.cp2.refresh_from_db()
        assert self.cp2.price == Decimal('23.00')

    @scopes_disabled()
    def test_budget_exceeded_in_first_position(self):
        self.v.budget = Decimal('1.00')
        self.v.save()
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.cp2.pk], 'admin@example.org', 'en', None, {},
                           'web')
        self.cp1.refresh_from_db()
        assert self.cp1.price == Decimal('22.00')
        self.cp2.refresh_from_db()
        assert self.cp2.price == Decimal('23.00')

    @scopes_disabled()
    def test_budget_exceeded_in_second_position(self):
        self.v.budget = Decimal('2.50')
        self.v.save()
        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.cp2.pk], 'admin@example.org', 'en', None, {},
                           'web')
        self.cp1.refresh_from_db()
        assert self.cp1.price == Decimal('21.50')
        self.cp2.refresh_from_db()
        assert self.cp2.price == Decimal('22.00')

    @scopes_disabled()
    def test_budget_exceeded_during_price_change(self):
        self.v.budget = Decimal('2.50')
        self.v.value = Decimal('21.00')
        self.v.save()
        self.cp1.expires = now() - timedelta(hours=1)
        self.cp1.save()
        self.cp2.expires = now() - timedelta(hours=1)
        self.cp2.save()

        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.cp2.pk], 'admin@example.org', 'en', None, {},
                           'web')
        self.cp1.refresh_from_db()
        assert self.cp1.price == Decimal('21.00')
        self.cp2.refresh_from_db()
        assert self.cp2.price == Decimal('22.50')

    @scopes_disabled()
    def test_budget_exceeded_expired_cart(self):
        self.v.budget = Decimal('0.00')
        self.v.value = Decimal('21.00')
        self.v.save()
        self.cp1.expires = now() - timedelta(hours=1)
        self.cp1.save()
        self.cp2.expires = now() - timedelta(hours=1)
        self.cp2.save()

        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp1.pk, self.cp2.pk], 'admin@example.org', 'en', None, {},
                           'web')
        self.cp1.refresh_from_db()
        assert self.cp1.price == Decimal('23.00')
        self.cp2.refresh_from_db()
        assert self.cp2.price == Decimal('23.00')

    @scopes_disabled()
    def test_budget_overbooked_expired_cart(self):
        self.v.budget = Decimal('1.50')
        self.v.value = Decimal('21.50')
        self.v.save()
        self.cp1.expires = now() - timedelta(hours=1)
        self.cp1.save()
        self.cp2.expires = now() - timedelta(hours=1)
        self.cp2.save()
        oid = _perform_order(self.event, self._manual_payment(), [self.cp1.pk], 'admin@example.org', 'en', None, {},
                             'web')
        o = Order.objects.get(pk=oid['order_id'])
        op = o.positions.first()

        assert op.item == self.ticket
        self.v.budget = Decimal('1.00')
        self.v.save()

        with self.assertRaises(OrderError):
            _perform_order(self.event, self._manual_payment(), [self.cp2.pk], 'admin@example.org', 'en', None, {},
                           'web')
        self.cp2.refresh_from_db()
        assert self.cp2.price == Decimal('23.00')


class CustomerCheckoutTestCase(BaseCheckoutTestCase, TestCase):

    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.orga.settings.customer_accounts = True
        self.event.settings.set('payment_stripe__enabled', True)
        self.event.settings.set('payment_banktransfer__enabled', True)
        with scopes_disabled():
            CartPosition.objects.create(
                event=self.event, cart_id=self.session_key, item=self.ticket,
                price=23, expires=now() + timedelta(minutes=10)
            )
            self.customer = self.orga.customers.create(email='john@example.org', is_verified=True)
            self.customer.set_password('foo')
            self.customer.save()

    def _finish(self):
        self._set_payment()
        self.client.post('/%s/%s/checkout/confirm/' % (self.orga.slug, self.event.slug), follow=True)
        with scopes_disabled():
            return Order.objects.last()

    def test_guest(self):
        response = self.client.get('/%s/%s/checkout/start' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'guest'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        order = self._finish()
        assert order.email == 'admin@localhost'
        assert not order.customer

    def test_guest_even_if_logged_in(self):
        self.client.post('/%s/account/login' % self.orga.slug, {
            'email': 'john@example.org',
            'password': 'foo',
        })

        response = self.client.get('/%s/%s/checkout/start' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'john@example.org' in response.content.decode()

        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'guest'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        order = self._finish()
        assert order.email == 'admin@localhost'
        assert not order.customer

    def test_login_already_logged_in_and_forced_email(self):
        self.client.post('/%s/account/login' % self.orga.slug, {
            'email': 'john@example.org',
            'password': 'foo',
        })

        response = self.client.get('/%s/%s/checkout/start' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert 'john@example.org' in response.content.decode()

        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'login'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'email': 'will-be-ignored'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        order = self._finish()
        assert order.email == 'john@example.org'
        assert order.customer == self.customer

    def test_login_valid(self):
        response = self.client.get('/%s/%s/checkout/start' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'login',
            'login-email': 'john@example.org',
            'login-password': 'foo',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        order = self._finish()
        assert order.customer == self.customer

    def test_login_valid_but_removed_after_logout(self):
        response = self.client.get('/%s/%s/checkout/start' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'login',
            'login-email': 'john@example.org',
            'login-password': 'foo',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        self.client.get('/%s/account/logout' % (self.orga.slug,), follow=True)

        response = self.client.get('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/?require_cookie=true' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert response.status_code == 200

    def test_login_invalid(self):
        response = self.client.get('/%s/%s/checkout/start' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'login',
            'login-email': 'john@example.org',
            'login-password': 'bar',
        }, follow=False)
        assert response.status_code == 200
        assert b'alert-danger' in response.content

    def test_register_valid(self):
        response = self.client.get('/%s/%s/checkout/start' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'register',
            'register-email': 'foo@example.com',
            'register-name_parts_0': 'John Doe',
        }, follow=False)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert len(djmail.outbox) == 1

        # After a valid registration form, we apply a kind of soft login. Since the email address hasn't yet been
        # verified, we do not do a proper login, since that would cause security problems. However, if the customer
        # goes back to this step manually, they can re-use the account.
        response = self.client.get('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug))
        assert response.content.decode().count('foo@example.com') == 1

        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'login',
        }, follow=False)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'email': 'will-be-ignored'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        order = self._finish()
        assert order.customer != self.customer
        assert order.customer.email == 'foo@example.com'
        assert order.email == 'foo@example.com'
        assert not order.customer.is_verified

    def test_register_invalid(self):
        response = self.client.get('/%s/%s/checkout/start' % (self.orga.slug, self.event.slug), follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'register',
            'register-email': 'john@example.org',
            'register-name_parts_0': 'John Doe',
        }, follow=False)
        assert response.status_code == 200
        assert b'has-error' in response.content

    def test_guest_not_allowed_if_granting_membership(self):
        self.ticket.grant_membership_type = self.orga.membership_types.create(
            name='Week pass'
        )
        self.ticket.save()
        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'guest'
        }, follow=False)
        assert response.status_code == 200

    def test_guest_not_allowed_if_requiring_membership(self):
        self.ticket.require_membership = True
        self.ticket.save()
        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'guest'
        }, follow=False)
        assert response.status_code == 200

    def test_native_auth_disabled(self):
        self.orga.settings.customer_accounts_native = False
        response = self.client.get('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug))
        assert b'register-email' not in response.content
        assert b'login-email' not in response.content

        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'register',
            'register-email': 'foo@example.com',
            'register-name_parts_0': 'John Doe',
        }, follow=False)
        assert response.status_code == 200

        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'login',
            'login-email': 'john@example.org',
            'login-password': 'foo',
        }, follow=False)
        assert response.status_code == 200

    def test_sso_login(self):
        with scopes_disabled():
            self.customer.provider = CustomerSSOProvider.objects.create(
                organizer=self.orga,
                method="oidc",
                name="OIDC OP",
                configuration={}
            )
            self.customer.save()
        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'login',
            'login-sso-data': dumps({'customer': self.customer.pk}, salt=f'customer_sso_popup_{self.orga.pk}'),
            'login-password': 'foo',
        }, follow=False)
        assert response.status_code == 302
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)

    def test_select_membership(self):
        mtype = self.orga.membership_types.create(name='Week pass', transferable=False)
        mtype2 = self.orga.membership_types.create(name='Invalid pass')
        self.ticket.require_membership = True
        self.ticket.require_membership_types.add(mtype)
        self.ticket.admission = True
        self.ticket.personalized = True
        self.ticket.save()
        self.event.settings.attendee_names_asked = True

        with scopes_disabled():
            cp = CartPosition.objects.get()
            m_correct1 = self.customer.memberships.create(
                membership_type=mtype,
                date_start=self.event.date_from - datetime.timedelta(days=1),
                date_end=self.event.date_from + datetime.timedelta(days=1),
                attendee_name_parts={'_scheme': 'full', 'full_name': 'John Doe'},
            )
            self.customer.memberships.create(
                membership_type=mtype,
                date_start=self.event.date_from - datetime.timedelta(days=1),
                date_end=self.event.date_from + datetime.timedelta(days=1),
                attendee_name_parts={'_scheme': 'full', 'full_name': 'Mark Fisher'},
            )
            self.customer.memberships.create(
                membership_type=mtype,
                date_start=self.event.date_from - datetime.timedelta(days=5),
                date_end=self.event.date_from - datetime.timedelta(days=1),
                attendee_name_parts={'_scheme': 'full', 'full_name': 'Sue Fisher'},
            )
            self.customer.memberships.create(
                membership_type=mtype2,
                date_start=self.event.date_from - datetime.timedelta(days=5),
                date_end=self.event.date_from + datetime.timedelta(days=1),
                attendee_name_parts={'_scheme': 'full', 'full_name': 'Mike Miller'},
            )

        response = self.client.post('/%s/%s/checkout/customer/' % (self.orga.slug, self.event.slug), {
            'customer_mode': 'login',
            'login-email': 'john@example.org',
            'login-password': 'foo',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/membership/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert b'John Doe' in response.content
        assert b'Mark Fisher' in response.content
        assert b'Sue Fisher' not in response.content
        assert b'Mike Miller' not in response.content

        response = self.client.post('/%s/%s/checkout/membership/' % (self.orga.slug, self.event.slug), {
            f'membership-{cp.pk}-membership': m_correct1.pk,
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        assert b'John Doe' in response.content
        assert b'Mark Fisher' not in response.content
        response = self.client.post('/%s/%s/checkout/questions/' % (self.orga.slug, self.event.slug), {
            'email': 'will-be-ignored',
            f'{cp.pk}-attendee_name_parts_0': 'will-be-ignored'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/checkout/payment/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        order = self._finish()
        assert order.customer == self.customer
        assert order.customer.email == order.email
        with scopes_disabled():
            assert order.positions.first().used_membership == m_correct1
            assert order.positions.first().attendee_name == 'John Doe'
