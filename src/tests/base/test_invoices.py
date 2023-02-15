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

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import DatabaseError, transaction
from django.utils.timezone import now
from django_countries.fields import Country
from django_scopes import scope, scopes_disabled

from pretix.base.models import (
    Event, ExchangeRate, Invoice, InvoiceAddress, Item, ItemVariation, Order,
    OrderPosition, Organizer,
)
from pretix.base.models.orders import OrderFee
from pretix.base.services.invoices import (
    build_preview_invoice_pdf, generate_cancellation, generate_invoice,
    invoice_pdf_task, invoice_qualified, regenerate_invoice,
)
from pretix.base.services.orders import OrderChangeManager


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    with scope(organizer=o):
        event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(), plugins='pretix.plugins.banktransfer'
        )
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now() + timedelta(days=10),
            total=0, locale='en'
        )
        tr = event.tax_rules.create(rate=Decimal('19.00'))
        o.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.25'), tax_rate=Decimal('19.00'),
                      tax_value=Decimal('0.05'), tax_rule=tr)
        ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                     category=None, default_price=23, tax_rule=tr,
                                     admission=True)
        t_shirt = Item.objects.create(event=event, name='T-Shirt',
                                      category=None, default_price=42, tax_rule=tr,
                                      admission=True)
        variation = ItemVariation.objects.create(value='M', item=t_shirt)
        OrderPosition.objects.create(
            order=o,
            item=ticket,
            variation=None,
            price=Decimal("23.00"),
            positionid=1,
        )
        OrderPosition.objects.create(
            order=o,
            item=t_shirt,
            variation=variation,
            price=Decimal("42.00"),
            positionid=2,
        )
        OrderPosition.objects.create(
            order=o,
            item=t_shirt,
            variation=variation,
            price=Decimal("42.00"),
            positionid=3,
            canceled=True
        )
        rates = {
            "USD": "1.1648",
            "RON": "4.5638",
            "CZK": "26.024",
            "BGN": "1.9558",
            "HRK": "7.4098",
            "EUR": "1.0000",
            "NOK": "9.3525",
            "HUF": "305.15",
            "DKK": "7.4361",
            "PLN": "4.2408",
            "GBP": "0.89350",
            "SEK": "9.5883"
        }
        for currency, rate in rates.items():
            ExchangeRate.objects.create(source_date=date.today(), source='eu:ecb:eurofxref-daily', source_currency='EUR', other_currency=currency, rate=rate)
        ExchangeRate.objects.create(source_date=date.today(), source='cz:cnb:rate-fixing-daily', source_currency='EUR',
                                    other_currency='CZK', rate=Decimal('25.0000'))
        yield event, o


@pytest.mark.django_db
def test_locale_setting(env):
    event, order = env
    event.settings.set('invoice_language', 'de')
    with scopes_disabled():
        inv = generate_invoice(order)
    assert inv.locale == 'de'


@pytest.mark.django_db
def test_locale_user(env):
    event, order = env
    order.locale = 'en'
    event.settings.set('invoice_language', '__user__')
    inv = generate_invoice(order)
    assert inv.locale == order.locale


@pytest.mark.django_db
def test_address_old_country(env):
    event, order = env
    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street',
                                  zipcode='12345', city='London', country_old='England', country='',
                                  order=order)
    inv = generate_invoice(order)
    assert inv.invoice_to == "Acme Company\n221B Baker Street\n12345 London\nEngland"


@pytest.mark.django_db
def test_address_with_state(env):
    event, order = env
    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street',
                                  zipcode='46530', city='Granger', country=Country('US'), state='IN',
                                  order=order)
    inv = generate_invoice(order)
    assert inv.invoice_to == "Acme Company\n221B Baker Street\n46530 Granger IN\nUnited States of America"


@pytest.mark.django_db
def test_address_with_state_long(env):
    event, order = env
    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street',
                                  zipcode='46530', city='Granger', country=Country('MY'), state='10',
                                  order=order)
    inv = generate_invoice(order)
    assert inv.invoice_to == "Acme Company\n221B Baker Street\n46530 Granger Selangor\nMalaysia"


@pytest.mark.django_db
def test_address(env):
    event, order = env
    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street',
                                  zipcode='12345', city='London', country=Country('GB'),
                                  order=order)
    inv = generate_invoice(order)
    assert inv.invoice_to == "Acme Company\n221B Baker Street\n12345 London\nUnited Kingdom"


@pytest.mark.django_db
def test_address_vat_id(env):
    event, order = env
    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street',
                                  name_parts={'full_name': 'Sherlock Holmes', '_scheme': 'full'},
                                  zipcode='12345',
                                  city='London',
                                  country_old='UK',
                                  country='', vat_id='UK1234567', order=order)
    inv = generate_invoice(order)
    assert inv.invoice_to == "Acme Company\nSherlock Holmes\n221B Baker Street\n12345 London\nUK\nVAT-ID: UK1234567"


@pytest.mark.django_db
def test_positions_skip_free(env):
    event, order = env
    event.settings.invoice_include_free = False
    op1 = order.positions.first()
    op1.price = Decimal('0.00')
    op1.save()
    inv = generate_invoice(order)
    assert inv.lines.count() == 2


@pytest.mark.django_db
def test_reverse_charge_note(env):
    event, order = env

    tr = event.tax_rules.first()
    tr.eu_reverse_charge = True
    tr.home_country = Country('DE')
    tr.save()

    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street', zipcode='12345', city='Warsaw',
                                  country=Country('PL'), vat_id='PL123456780', vat_id_validated=True, order=order,
                                  is_business=True)

    ocm = OrderChangeManager(order, None)
    ocm.recalculate_taxes()
    ocm.commit()
    assert not order.positions.filter(tax_value__gt=0).exists()

    inv = generate_invoice(order)
    assert "reverse charge" in inv.additional_text.lower()
    assert inv.foreign_currency_display == "PLN"
    assert inv.foreign_currency_rate == Decimal("4.2408")
    assert inv.foreign_currency_rate_date == date.today()
    assert inv.foreign_currency_source == 'eu:ecb:eurofxref-daily'


@pytest.mark.django_db
def test_custom_tax_note(env):
    event, order = env

    tr = event.tax_rules.first()
    tr.eu_reverse_charge = True
    tr.home_country = Country('DE')
    tr.custom_rules = json.dumps([
        {
            'country': 'PL',
            'address_type': '',
            'action': 'vat',
            'rate': '20',
            'invoice_text': {
                'de': 'Polnische Steuer anwendbar',
                'en': 'Polish tax applies'
            }
        }
    ])
    tr.save()

    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street', zipcode='12345', city='Warsaw',
                                  country=Country('PL'), vat_id='PL123456780', vat_id_validated=True, order=order,
                                  is_business=True)

    ocm = OrderChangeManager(order, None)
    ocm.recalculate_taxes()
    ocm.commit()

    inv = generate_invoice(order)
    assert "Polish tax applies" in inv.additional_text


@pytest.mark.django_db
def test_reverse_charge_foreign_currency_data_too_old(env):
    event, order = env
    ExchangeRate.objects.update(source_date=date.today() - timedelta(days=14))

    tr = event.tax_rules.first()
    tr.eu_reverse_charge = True
    tr.home_country = Country('DE')
    tr.save()

    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street', zipcode='12345', city='Warsaw',
                                  country=Country('PL'), vat_id='PL123456780', vat_id_validated=True, order=order,
                                  is_business=True)

    ocm = OrderChangeManager(order, None)
    ocm.recalculate_taxes()
    ocm.commit()
    assert not order.positions.filter(tax_value__gt=0).exists()

    inv = generate_invoice(order)
    assert "reverse charge" in inv.additional_text.lower()
    assert inv.foreign_currency_rate is None
    assert inv.foreign_currency_rate_date is None


@pytest.mark.django_db
def test_reverse_charge_foreign_currency_disabled(env):
    event, order = env
    event.settings.invoice_eu_currencies = 'False'

    tr = event.tax_rules.first()
    tr.eu_reverse_charge = True
    tr.home_country = Country('DE')
    tr.save()

    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street', zipcode='12345', city='Warsaw',
                                  country=Country('PL'), vat_id='PL123456780', vat_id_validated=True, order=order,
                                  is_business=True)

    ocm = OrderChangeManager(order, None)
    ocm.recalculate_taxes()
    ocm.commit()
    assert not order.positions.filter(tax_value__gt=0).exists()

    inv = generate_invoice(order)
    assert "reverse charge" in inv.additional_text.lower()
    assert inv.foreign_currency_rate is None
    assert inv.foreign_currency_rate_date is None


@pytest.mark.django_db
def test_invoice_indirect_currency_conversion(env):
    event, order = env
    event.currency = 'SEK'
    event.save()

    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street', zipcode='12345', city='Warsaw',
                                  country=Country('PL'), vat_id='PL123456780', vat_id_validated=True, order=order,
                                  is_business=True)

    inv = generate_invoice(order)
    assert inv.foreign_currency_display == "PLN"
    assert inv.foreign_currency_rate == Decimal("0.4423")
    assert inv.foreign_currency_rate_date == date.today()
    assert inv.foreign_currency_source == 'eu:ecb:eurofxref-daily'


@pytest.mark.django_db
def test_invoice_czk_currency_conversion(env):
    event, order = env
    event.settings.invoice_eu_currencies = 'CZK'

    event.settings.set('invoice_language', 'en')
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street', zipcode='12345', city='Warsaw',
                                  country=Country('PL'), vat_id='PL123456780', vat_id_validated=True, order=order,
                                  is_business=True)

    inv = generate_invoice(order)
    assert inv.foreign_currency_display == "CZK"
    assert inv.foreign_currency_rate == Decimal("25.0000")
    assert inv.foreign_currency_rate_date == date.today()
    assert inv.foreign_currency_source == 'cz:cnb:rate-fixing-daily'


@pytest.mark.django_db
def test_positions(env):
    event, order = env
    inv = generate_invoice(order)
    assert inv.lines.count() == 3
    first = inv.lines.first()
    assert 'Early-bird' in first.description
    assert first.gross_value == Decimal('23.00')

    second = inv.lines.all()[1]
    assert 'T-Shirt' in second.description
    assert 'M' in second.description
    assert second.gross_value == Decimal('42.00')

    last = inv.lines.last()
    assert 'Payment' in last.description
    fee = order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
    assert last.gross_value == fee.value
    assert last.tax_rate == fee.tax_rate
    assert last.tax_value == fee.tax_value
    assert last.fee_type == 'payment'
    assert inv.invoice_to == ""


@pytest.mark.django_db
def test_rebuilding(env):
    event, order = env
    inv = generate_invoice(order)
    inv2 = regenerate_invoice(inv)
    assert inv.order == inv2.order

    inv3 = generate_cancellation(inv)
    inv4 = regenerate_invoice(inv3)
    assert inv3.order == inv4.order


@pytest.mark.django_db
def test_cannot_delete_invoice(env):
    event, order = env
    inv = generate_invoice(order)
    with pytest.raises(Exception):
        inv.delete()


@pytest.mark.django_db
def test_cannot_write_invoice_without_order(env):
    event, _ = env
    with pytest.raises(Exception):
        i = Invoice(order=None, event=event)
        i.save()


@pytest.mark.django_db
def test_pdf_generation(env):
    event, order = env
    inv = generate_invoice(order)
    cancellation = generate_cancellation(inv)
    assert invoice_pdf_task(inv.pk)
    assert invoice_pdf_task(cancellation.pk)


@pytest.mark.django_db
def test_pdf_generation_custom_text(env):
    event, order = env
    event.settings.set('invoice_introductory_text', 'introductory invoice text')
    # set a really long additional text, to make the invoice span two pages
    event.settings.set('invoice_additional_text', 'additional invoice text\n' * 100)
    event.settings.set('show_date_to', False)
    inv = generate_invoice(order)
    assert invoice_pdf_task(inv.pk)


@pytest.mark.django_db
def test_pdf_preview_generation(env):
    event, order = env
    assert build_preview_invoice_pdf(event)


@pytest.mark.django_db
def test_invoice_numbers(env):
    event, order = env
    order2 = Order.objects.create(
        code='BAR', event=event, email='dummy2@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0,
        locale='en'
    )
    order2.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.25'), tax_rate=Decimal('0.00'),
                       tax_value=Decimal('0.00'))
    testorder = Order.objects.create(
        code='BAR', event=event, email='dummy2@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0, testmode=True,
        locale='en'
    )
    inv1 = generate_invoice(order)
    inv2 = generate_invoice(order)
    invt1 = generate_invoice(testorder)

    event.settings.set('invoice_numbers_consecutive', False)
    inv3 = generate_invoice(order)
    inv4 = generate_invoice(order)
    inv21 = generate_invoice(order2)
    invt2 = generate_invoice(testorder)
    inv22 = generate_invoice(order2)

    event.settings.set('invoice_numbers_consecutive', True)
    inv5 = generate_invoice(order)
    inv6 = generate_invoice(order)
    invt3 = generate_invoice(testorder)
    inv7 = generate_invoice(order)
    Invoice.objects.filter(pk=inv6.pk).delete()  # This should never ever happen, but what if it happens anyway?
    inv8 = generate_invoice(order)
    inv23 = generate_invoice(order2)

    event.settings.set('invoice_numbers_counter_length', 6)
    inv24 = generate_invoice(order)
    event.settings.set('invoice_numbers_counter_length', 1)
    inv25 = generate_invoice(order)
    inv26 = generate_invoice(order)

    # expected behaviour for switching between numbering formats or dealing with gaps
    assert inv1.invoice_no == '00001'
    assert inv2.invoice_no == '00002'
    assert inv3.invoice_no == '{}-1'.format(order.code)
    assert inv4.invoice_no == '{}-2'.format(order.code)
    assert inv5.invoice_no == '00003'
    assert inv6.invoice_no == '00004'
    assert inv7.invoice_no == '00005'
    assert inv8.invoice_no == '00006'

    # test that separate orders are counted separately in this mode
    assert inv21.invoice_no == '{}-1'.format(order2.code)
    assert inv22.invoice_no == '{}-2'.format(order2.code)
    # but consecutively in this mode
    assert inv23.invoice_no == '00007'
    assert inv24.invoice_no == '000008'
    assert inv25.invoice_no == '9'
    assert inv26.invoice_no == '10'

    # test Invoice.number, too
    assert inv1.number == '{}-00001'.format(event.slug.upper())
    assert inv3.number == '{}-{}-1'.format(event.slug.upper(), order.code)

    assert invt1.number == '{}-TEST-00001'.format(event.slug.upper())
    assert invt2.number == '{}-TEST-{}-1'.format(event.slug.upper(), testorder.code)
    assert invt3.number == '{}-TEST-00002'.format(event.slug.upper())


@pytest.mark.django_db
def test_invoice_number_prefixes(env):
    event, order = env
    event2 = Event.objects.create(
        organizer=event.organizer, name='Dummy', slug='dummy2',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    order2 = Order.objects.create(
        event=event2, email='dummy2@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0,
        locale='en'
    )
    order2.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.25'), tax_rate=Decimal('0.00'),
                       tax_value=Decimal('0.00'))
    event.settings.set('invoice_numbers_consecutive', False)
    event2.settings.set('invoice_numbers_consecutive', False)
    assert generate_invoice(order).number == 'DUMMY-{}-1'.format(order.code)
    assert generate_invoice(order2).number == 'DUMMY2-{}-1'.format(order2.code)

    event.settings.set('invoice_numbers_consecutive', True)
    event2.settings.set('invoice_numbers_consecutive', True)
    event.settings.set('invoice_numbers_prefix', '')
    event2.settings.set('invoice_numbers_prefix', '')

    assert generate_invoice(order).number == 'DUMMY-00001'
    assert generate_invoice(order).number == 'DUMMY-00002'
    assert generate_invoice(order2).number == 'DUMMY2-00001'
    assert generate_invoice(order2).number == 'DUMMY2-00002'

    event.settings.set('invoice_numbers_prefix', 'shared_')
    event2.settings.set('invoice_numbers_prefix', 'shared_')

    assert generate_invoice(order).number == 'shared_00001'
    assert generate_invoice(order2).number == 'shared_00002'
    assert generate_invoice(order).number == 'shared_00003'
    assert generate_invoice(order2).number == 'shared_00004'

    event.settings.set('invoice_numbers_consecutive', False)
    event2.settings.set('invoice_numbers_consecutive', False)
    assert generate_invoice(order).number == 'shared_{}-1'.format(order.code)
    assert generate_invoice(order2).number == 'shared_{}-1'.format(order2.code)

    event2.settings.set('invoice_numbers_prefix', 'inv_')
    event2.settings.set('invoice_numbers_prefix_cancellations', 'crd_')
    event2.settings.set('invoice_numbers_consecutive', True)
    event2.settings.set('invoice_numbers_counter_length', 4)
    i = generate_invoice(order2)
    assert i.number == 'inv_0001'
    ci = generate_cancellation(i)
    assert ci.number == 'crd_0001'
    assert ci.full_invoice_no == 'crd_0001'

    event2.settings.set('invoice_numbers_consecutive', False)
    i = generate_invoice(order2)
    assert i.number == f'inv_{order2.code}-1'
    assert generate_cancellation(i).number == f'crd_{order2.code}-1'

    event2.settings.set('invoice_numbers_consecutive', True)
    event2.settings.set('invoice_numbers_prefix', 'inv_%Y%m%d_')
    i = generate_invoice(order2)
    assert i.number == 'inv_%s_0001' % now().date().strftime('%Y%m%d')

    # Test database uniqueness check
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Invoice.objects.create(
                order=order,
                event=order.event,
                organizer=order.event.organizer,
                date=now().date(),
                locale='en',
                invoice_no='00001',
            )


@pytest.mark.django_db
def test_sales_channels_qualify(env):
    event, order = env
    event.settings.set('invoice_generate', 'admin')

    # Orders with Total of 0 do never qualify
    assert invoice_qualified(order) is False

    order.total = Decimal('42.00')

    # Order with default Sales Channel (web)
    assert invoice_qualified(order) is True

    event.settings.set('invoice_generate_sales_channels', [])
    assert invoice_qualified(order) is False
