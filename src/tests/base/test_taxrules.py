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
import json
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_countries.fields import Country
from django_scopes import scope

from pretix.base.models import (
    Event, InvoiceAddress, OrderFee, OrderPosition, Organizer, TaxRule,
)
from pretix.base.models.tax import TaxedPrice
from pretix.base.services.tax import split_fee_for_taxes


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    with scope(organizer=o):
        yield event


@pytest.mark.django_db
def test_from_gross_price(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        code='S/standard',
        price_includes_tax=True
    )
    tp = tr.tax(Decimal('100.00'))
    assert tp.gross == Decimal('100')
    assert tp.net == Decimal('90.91')
    assert tp.tax == Decimal('100.00') - Decimal('90.91')
    assert tp.rate == Decimal('10.00')
    assert tp.code == 'S/standard'

    tr = TaxRule(
        event=event,
        rate=Decimal('19.00'),
        code=None,
        price_includes_tax=True,
    )
    tp = tr.tax(Decimal('99.99'))
    assert tp.gross == Decimal('99.99')
    assert tp.net == Decimal('84.03')
    assert tp.tax == Decimal('15.96')
    assert tp.rate == Decimal('19.00')
    assert tp.code is None


@pytest.mark.django_db
def test_from_net_price(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        code=None,
        price_includes_tax=False,
    )
    tp = tr.tax(Decimal('100.00'))
    assert tp.gross == Decimal('110.00')
    assert tp.net == Decimal('100.00')
    assert tp.tax == Decimal('10.00')
    assert tp.rate == Decimal('10.00')
    assert tp.code is None


@pytest.mark.django_db
def test_reverse_charge_no_address(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=True,
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False,
    )
    assert not tr.is_reverse_charge(None)
    assert tr._tax_applicable(None)
    assert tr.tax_code_for(None) == "S/standard"


@pytest.mark.django_db
def test_reverse_charge_no_country(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=True,
        rate=Decimal('10.00'),
        price_includes_tax=False,
        code="S/standard",
    )
    ia = InvoiceAddress(
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax_code_for(ia) == "S/standard"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code="S/standard",
    )


@pytest.mark.django_db
def test_reverse_charge_individual_same_country(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=True,
        home_country=Country('DE'),
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False,
    )
    ia = InvoiceAddress(
        is_business=False,
        country=Country('DE')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax_code_for(ia) == "S/standard"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code="S/standard",
    )


@pytest.mark.django_db
def test_reverse_charge_individual_eu(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=True,
        home_country=Country('DE'),
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False
    )
    ia = InvoiceAddress(
        is_business=False,
        country=Country('AT')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax_code_for(ia) == "S/standard"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code="S/standard",
    )


@pytest.mark.django_db
def test_reverse_charge_individual_3rdc(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=True,
        home_country=Country('DE'),
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False
    )
    ia = InvoiceAddress(
        is_business=False,
        country=Country('US')
    )
    assert not tr.is_reverse_charge(ia)
    assert not tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('0.00')
    assert tr.tax_code_for(ia) == "O"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('100.00'),
        net=Decimal('100.00'),
        tax=Decimal('0.00'),
        rate=Decimal('0.00'),
        name='',
        code='O',
    )


@pytest.mark.django_db
def test_reverse_charge_business_same_country(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=True,
        home_country=Country('DE'),
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('DE')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax_code_for(ia) == "S/standard"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code="S/standard",
    )


@pytest.mark.django_db
def test_reverse_charge_business_eu(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=True,
        home_country=Country('DE'),
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('AT')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax_code_for(ia) == "S/standard"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code="S/standard",
    )


@pytest.mark.django_db
def test_reverse_charge_business_3rdc(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=True,
        home_country=Country('DE'),
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('US')
    )
    assert not tr.is_reverse_charge(ia)
    assert not tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('0.00')
    assert tr.tax_code_for(ia) == "O"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('100.00'),
        net=Decimal('100.00'),
        tax=Decimal('0.00'),
        rate=Decimal('0.00'),
        name='',
        code='O',
    )


@pytest.mark.django_db
def test_reverse_charge_valid_vat_id_business_same_country(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=True,
        home_country=Country('DE'),
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('DE'),
        vat_id='DE123456',
        vat_id_validated=True
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax_code_for(ia) == "S/standard"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code="S/standard",
    )


@pytest.mark.django_db
def test_reverse_charge_valid_vat_id_business_eu(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=True,
        home_country=Country('DE'),
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False
    )
    ia = InvoiceAddress(
        is_business=True,
        vat_id='AT12346',
        vat_id_validated=True,
        country=Country('AT')
    )
    assert tr.is_reverse_charge(ia)
    assert not tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('0.00')
    assert tr.tax_code_for(ia) == "AE"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('100.00'),
        net=Decimal('100.00'),
        tax=Decimal('0.00'),
        rate=Decimal('0.00'),
        name='',
        code='AE',
    )


@pytest.mark.django_db
def test_reverse_charge_valid_vat_id_business_3rdc(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=True,
        home_country=Country('DE'),
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('US'),
        vat_id='US12346',
        vat_id_validated=True
    )
    assert not tr.is_reverse_charge(ia)
    assert not tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('0.00')
    assert tr.tax_code_for(ia) == "O"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('100.00'),
        net=Decimal('100.00'),
        tax=Decimal('0.00'),
        rate=Decimal('0.00'),
        name='',
        code='O',
    )


@pytest.mark.django_db
def test_reverse_charge_disabled(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=False,
        home_country=Country('DE'),
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False
    )
    ia = InvoiceAddress(
        is_business=True,
        vat_id='AT12346',
        vat_id_validated=True,
        country=Country('AT')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax_code_for(ia) == "S/standard"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code="S/standard",
    )


@pytest.mark.django_db
def test_custom_rules_override(event):
    tr = TaxRule(
        event=event,
        eu_reverse_charge=True,
        home_country=Country('DE'),
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False,
        custom_rules=json.dumps([
            {'country': 'ZZ', 'address_type': '', 'action': 'vat'}
        ])
    )
    ia = InvoiceAddress(
        is_business=True,
        vat_id='AT12346',
        vat_id_validated=True,
        country=Country('AT')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax_code_for(ia) == "S/standard"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code="S/standard",
    )


@pytest.mark.django_db
def test_custom_rules_in_order(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False,
        custom_rules=json.dumps([
            {'country': 'ZZ', 'address_type': '', 'action': 'vat', 'code': 'S/reduced'},
            {'country': 'ZZ', 'address_type': '', 'action': 'reverse'}
        ])
    )
    ia = InvoiceAddress(
        is_business=True,
        vat_id='AT12346',
        vat_id_validated=True,
        country=Country('AT')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax_code_for(ia) == "S/reduced"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code="S/reduced",
    )


@pytest.mark.django_db
def test_custom_rules_any_country(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False,
        custom_rules=json.dumps([
            {'country': 'ZZ', 'address_type': '', 'action': 'no', 'code': 'O'},
        ])
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('AT')
    )
    assert not tr.is_reverse_charge(ia)
    assert not tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('0.00')
    assert tr.tax_code_for(ia) == "O"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('100.00'),
        net=Decimal('100.00'),
        tax=Decimal('0.00'),
        rate=Decimal('0.00'),
        name='',
        code="O",
    )


@pytest.mark.django_db
def test_custom_rules_eu_country(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False,
        custom_rules=json.dumps([
            {'country': 'EU', 'address_type': '', 'action': 'no', 'code': 'Z'},
        ])
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('AT')
    )
    assert not tr.is_reverse_charge(ia)
    assert not tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('0.00')
    assert tr.tax_code_for(ia) == "Z"
    ia = InvoiceAddress(
        is_business=True,
        country=Country('US')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_code_for(ia) == "S/standard"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code="S/standard",
    )


@pytest.mark.django_db
def test_custom_rules_specific_country(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        code="S/standard",
        price_includes_tax=False,
        custom_rules=json.dumps([
            {'country': 'AT', 'address_type': '', 'action': 'no', 'code': 'Z'},
        ])
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('AT')
    )
    assert not tr.is_reverse_charge(ia)
    assert not tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('0.00')
    assert tr.tax_code_for(ia) == "Z"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('100.00'),
        net=Decimal('100.00'),
        tax=Decimal('0.00'),
        rate=Decimal('0.00'),
        name='',
        code="Z",
    )

    ia = InvoiceAddress(
        is_business=True,
        country=Country('DE')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code="S/standard",
    )


@pytest.mark.django_db
def test_custom_rules_specific_state(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        price_includes_tax=False,
        custom_rules=json.dumps([
            {'country': 'US-NY', 'address_type': '', 'action': 'vat', 'rate': '20.00'},
            {'country': 'US-DE', 'address_type': '', 'action': 'no'},
            {'country': 'US', 'address_type': '', 'action': 'vat', 'rate': '30.00'},
        ])
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('DE')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code=None,
    )

    ia = InvoiceAddress(
        is_business=True,
        country=Country('US'),
        state='NC'
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('30.00')
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('130.00'),
        net=Decimal('100.00'),
        tax=Decimal('30.00'),
        rate=Decimal('30.00'),
        name='',
        code=None,
    )

    ia = InvoiceAddress(
        is_business=True,
        country=Country('US'),
        state='NY'
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('20.00')
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('120.00'),
        net=Decimal('100.00'),
        tax=Decimal('20.00'),
        rate=Decimal('20.00'),
        name='',
        code=None,
    )

    ia = InvoiceAddress(
        is_business=True,
        country=Country('US'),
        state='DE'
    )
    assert not tr.is_reverse_charge(ia)
    assert not tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('0.00')
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('100.00'),
        net=Decimal('100.00'),
        tax=Decimal('0.00'),
        rate=Decimal('0.00'),
        name='',
        code=None,
    )


@pytest.mark.django_db
def test_custom_rules_individual(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        price_includes_tax=False,
        custom_rules=json.dumps([
            {'country': 'ZZ', 'address_type': 'individual', 'action': 'no'},
        ])
    )
    ia = InvoiceAddress(
        is_business=False,
        country=Country('AT')
    )
    assert not tr.is_reverse_charge(ia)
    assert not tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('0.00')
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('100.00'),
        net=Decimal('100.00'),
        tax=Decimal('0.00'),
        rate=Decimal('0.00'),
        name='',
        code=None,
    )

    ia = InvoiceAddress(
        is_business=True,
        country=Country('DE')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code=None,
    )


@pytest.mark.django_db
def test_custom_rules_business(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        price_includes_tax=False,
        custom_rules=json.dumps([
            {'country': 'ZZ', 'address_type': 'business', 'action': 'no'},
        ])
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('AT')
    )
    assert not tr.is_reverse_charge(ia)
    assert not tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('0.00')
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('100.00'),
        net=Decimal('100.00'),
        tax=Decimal('0.00'),
        rate=Decimal('0.00'),
        name='',
        code=None,
    )

    ia = InvoiceAddress(
        is_business=False,
        country=Country('DE')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code=None,
    )


@pytest.mark.django_db
def test_custom_rules_vat_id(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        price_includes_tax=False,
        code="S/standard",
        custom_rules=json.dumps([
            {'country': 'EU', 'address_type': 'business_vat_id', 'action': 'reverse'},
        ])
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('AT')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax_code_for(ia) == "S/standard"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code="S/standard",
    )

    ia = InvoiceAddress(
        is_business=True,
        country=Country('DE'),
        vat_id='DE1234',
        vat_id_validated=True
    )
    assert tr.is_reverse_charge(ia)
    assert not tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('0.00')
    assert tr.tax_code_for(ia) == "AE"
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('100.00'),
        net=Decimal('100.00'),
        tax=Decimal('0.00'),
        rate=Decimal('0.00'),
        name='',
        code='AE',
    )


@pytest.mark.django_db
def test_custom_rules_country_rate(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        price_includes_tax=False,
        custom_rules=json.dumps([
            {'country': 'EU', 'address_type': 'business_vat_id', 'action': 'vat', 'rate': '100.00'},
        ])
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('DE')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code=None,
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('DE'),
        vat_id='DE1234',
        vat_id_validated=True
    )
    assert tr.tax_rate_for(ia) == Decimal('100.00')
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('200.00'),
        net=Decimal('100.00'),
        tax=Decimal('100.00'),
        rate=Decimal('100.00'),
        name='',
        code=None,
    )


@pytest.mark.django_db
def test_custom_rules_country_rate_keep_gross_if_rate_changes(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        price_includes_tax=False,
        keep_gross_if_rate_changes=True,
        custom_rules=json.dumps([
            {'country': 'EU', 'address_type': 'business_vat_id', 'action': 'vat', 'rate': '100.00'},
        ])
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('DE')
    )
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax_rate_for(ia) == Decimal('10.00')
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('100.00'),
        tax=Decimal('10.00'),
        rate=Decimal('10.00'),
        name='',
        code=None,
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('DE'),
        vat_id='DE1234',
        vat_id_validated=True
    )
    assert tr.tax_rate_for(ia) == Decimal('100.00')
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax(Decimal('100.00'), invoice_address=ia) == TaxedPrice(
        gross=Decimal('110.00'),
        net=Decimal('55.00'),
        tax=Decimal('55.00'),
        rate=Decimal('100.00'),
        name='',
        code=None,
    )


@pytest.mark.django_db
def test_custom_rules_country_rate_subtract_from_gross(event):
    tr = TaxRule(
        event=event,
        rate=Decimal('10.00'),
        price_includes_tax=False,
        custom_rules=json.dumps([
            {'country': 'EU', 'address_type': 'business_vat_id', 'action': 'vat', 'rate': '100.00'},
        ])
    )
    ia = InvoiceAddress(
        is_business=True,
        country=Country('DE'),
        vat_id='DE1234',
        vat_id_validated=True
    )
    assert tr.tax_rate_for(ia) == Decimal('100.00')
    assert not tr.is_reverse_charge(ia)
    assert tr._tax_applicable(ia)
    assert tr.tax(Decimal('100.00'), invoice_address=ia, subtract_from_gross=Decimal('20.00')) == TaxedPrice(
        gross=Decimal('163.64'),  # ((100 * 1.1) - 20) / (1 + 10%) * (1 + 100%)
        net=Decimal('81.82'),
        tax=Decimal('81.82'),
        rate=Decimal('100.00'),
        name='',
        code=None,
    )


@pytest.mark.django_db
def test_no_negative_due_to_subtract_from_gross(event):
    tr = TaxRule(
        event=event,
        rate=Decimal("19.00"),
        price_includes_tax=True,
    )
    assert tr.tax(Decimal('100.00'), subtract_from_gross=Decimal('200.00')).gross == Decimal("0.00")
    tr = TaxRule(
        event=event,
        rate=Decimal("0.00"),
        price_includes_tax=True,
    )
    assert tr.tax(Decimal('100.00'), subtract_from_gross=Decimal('200.00')).gross == Decimal("0.00")
    tr = TaxRule(
        event=event,
        rate=Decimal("19.00"),
        price_includes_tax=False,
    )
    assert tr.tax(Decimal('100.00'), subtract_from_gross=Decimal('200.00')).gross == Decimal("0.00")
    tr = TaxRule(
        event=event,
        rate=Decimal("19.00"),
        price_includes_tax=True,
    )
    assert tr.tax(Decimal('100.00'), subtract_from_gross=Decimal('200.00')).gross == Decimal("0.00")


@pytest.mark.django_db
def test_allow_negative(event):
    tr = TaxRule(
        event=event,
        rate=Decimal("19.00"),
        price_includes_tax=True,
    )
    assert tr.tax(Decimal('-100.00')).gross == Decimal("-100.00")
    tr = TaxRule(
        event=event,
        rate=Decimal("0.00"),
        price_includes_tax=True,
    )
    assert tr.tax(Decimal('-100.00')).gross == Decimal("-100.00")
    tr = TaxRule(
        event=event,
        rate=Decimal("19.00"),
        price_includes_tax=False,
    )
    assert tr.tax(Decimal('-100.00')).gross == Decimal("-119.00")
    tr = TaxRule(
        event=event,
        rate=Decimal("19.00"),
        price_includes_tax=True,
    )
    assert tr.tax(Decimal('-100.00')).gross == Decimal("-100.00")


@pytest.mark.django_db
def test_split_fees(event):
    tr19 = TaxRule(rate=Decimal("19.00"), pk=1)
    tr7 = TaxRule(rate=Decimal("7.00"), pk=2)
    item = event.items.create(name="Budget Ticket", default_price=23)

    op1 = OrderPosition(price=Decimal("11.90"), item=item)
    op1._calculate_tax(tax_rule=tr19, invoice_address=InvoiceAddress())
    op2 = OrderPosition(price=Decimal("10.70"), item=item)
    op2._calculate_tax(tax_rule=tr7, invoice_address=InvoiceAddress())
    of1 = OrderFee(value=Decimal("5.00"), fee_type=OrderFee.FEE_TYPE_SHIPPING)
    of1._calculate_tax(tax_rule=tr7, invoice_address=InvoiceAddress(), event=event)

    # Example of a 10% service fee
    assert split_fee_for_taxes([op1, op2], Decimal("2.26"), event) == [
        (tr7, Decimal("1.07")),
        (tr19, Decimal("1.19")),
    ]

    # Example of a full cancellation fee
    assert split_fee_for_taxes([op1, op2], Decimal("22.60"), event) == [
        (tr7, Decimal("10.70")),
        (tr19, Decimal("11.90")),
    ]
    assert split_fee_for_taxes([op1, op2, of1], Decimal("27.60"), event) == [
        (tr7, Decimal("15.70")),
        (tr19, Decimal("11.90")),
    ]

    # Example that rounding always is done with benefit to the highest tax rate
    assert split_fee_for_taxes([op1, op2], Decimal("0.03"), event) == [
        (tr7, Decimal("0.01")),
        (tr19, Decimal("0.02")),
    ]
