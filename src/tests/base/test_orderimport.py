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
import csv
import datetime
from decimal import Decimal
from io import StringIO

import pytest
from django.core.files.base import ContentFile
from django.utils.timezone import now
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString

from pretix.base.models import (
    CachedFile, Event, Item, Order, OrderPayment, OrderPosition, Organizer,
    Question, QuestionAnswer, User,
)
from pretix.base.services.orderimport import DataImportError, import_orders


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.paypal'
    )
    return event


@pytest.fixture
def item(event):
    return Item.objects.create(event=event, name="Ticket", default_price=23)


@pytest.fixture
def user():
    return User.objects.create_user('test@localhost', 'test')


def inputfile_factory():
    d = [
        {
            'A': 'Dieter',
            'B': 'Schneider',
            'C': 'schneider@example.org',
            'D': 'Test',
            'E': 'Foo',
            'F': '0.00',
            'G': 'US',
            'H': 'Texas',
            'I': 'Foo',
            'J': '2021-06-28 11:00:00',
            'K': '06221/32177-50',
        },
        {
            'A': 'Daniel',
            'B': 'Wulf',
            'C': 'daniel@example.org',
            'D': 'Test',
            'E': 'Bar',
            'F': '0.00',
            'G': 'DE',
            'H': '',
            'I': 'Bar',
            'J': '2021-06-28 11:00:00',
            'K': '+4962213217750',
        },
        {},
        {
            'A': 'Anke',
            'B': 'Müller',
            'C': '',
            'D': 'Test',
            'E': 'Baz',
            'F': '0.00',
            'G': 'XK',
            'H': '',
            'I': 'Foo,Bar',
            'J': '2021-06-28 11:00:00',
            'K': '',
        },
    ]
    f = StringIO()
    w = csv.DictWriter(f, ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K'], dialect=csv.excel)
    w.writeheader()
    w.writerows(d)
    f.seek(0)
    c = CachedFile.objects.create(type="text/csv", filename="input.csv")
    c.file.save("input.csv", ContentFile(f.read()))
    return c


DEFAULT_SETTINGS = {
    'orders': 'many',
    'testmode': False,
    'status': 'paid',
    'email': 'empty',
    'phone': 'empty',
    'variation': 'empty',
    'invoice_address_company': 'empty',
    'invoice_address_name_full_name': 'empty',
    'invoice_address_street': 'empty',
    'invoice_address_zipcode': 'empty',
    'invoice_address_city': 'empty',
    'invoice_address_country': 'static:DE',
    'invoice_address_state': 'empty',
    'invoice_address_vat_id': 'empty',
    'invoice_address_internal_reference': 'empty',
    'attendee_name_full_name': 'empty',
    'attendee_email': 'empty',
    'price': 'empty',
    'secret': 'empty',
    'locale': 'static:en',
    'sales_channel': 'static:web',
    'comment': 'empty'
}


@pytest.mark.django_db
@scopes_disabled()
def test_import_simple(event, item, user):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert event.orders.count() == 3
    assert OrderPosition.objects.count() == 3


@pytest.mark.django_db
@scopes_disabled()
def test_import_as_one_order(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['orders'] = 'one'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert event.orders.count() == 1
    o = event.orders.get()
    assert o.positions.count() == 3
    assert set(pos.positionid for pos in o.positions.all()) == {1, 2, 3}


@pytest.mark.django_db
@scopes_disabled()
def test_import_in_test_mode(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['testmode'] = True
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert event.orders.last().testmode


@pytest.mark.django_db
@scopes_disabled()
def test_import_not_in_test_mode(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['testmode'] = False
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert not event.orders.last().testmode


@pytest.mark.django_db
@scopes_disabled()
def test_import_pending(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['status'] = 'pending'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    o = event.orders.last()
    assert o.status == Order.STATUS_PENDING
    assert o.total == Decimal('23.00')
    assert not o.payments.exists()


@pytest.mark.django_db
@scopes_disabled()
def test_import_paid_generate_invoice(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['status'] = 'paid'
    event.settings.invoice_generate = 'paid'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    o = event.orders.last()
    assert o.status == Order.STATUS_PAID
    assert o.total == Decimal('23.00')
    p = o.payments.first()
    assert p.provider == 'manual'
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    assert o.invoices.count() == 1


@pytest.mark.django_db
@scopes_disabled()
def test_import_free(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['price'] = 'csv:F'
    settings['status'] = 'pending'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    o = event.orders.last()
    assert o.status == Order.STATUS_PAID
    assert o.total == Decimal('0.00')
    p = o.payments.first()
    assert p.provider == 'free'
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED


@pytest.mark.django_db
@scopes_disabled()
def test_import_email(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['email'] = 'csv:C'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert event.orders.filter(email="schneider@example.org").exists()
    assert event.orders.filter(email="daniel@example.org").exists()
    assert event.orders.filter(email__isnull=True).count() == 1


@pytest.mark.django_db
@scopes_disabled()
def test_import_email_invalid(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['email'] = 'csv:A'
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Dieter" for column "E-mail address" in line "1": Enter a valid email address.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_phone(user, event, item):
    event.settings.region = 'DE'
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['email'] = 'csv:C'
    settings['phone'] = 'csv:K'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert str(event.orders.get(email="schneider@example.org").phone) == "+4962213217750"
    assert str(event.orders.get(email="daniel@example.org").phone) == "+4962213217750"
    assert event.orders.filter(phone__isnull=True).count() == 1


@pytest.mark.django_db
@scopes_disabled()
def test_import_phone_invalid(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['phone'] = 'csv:A'
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Dieter" for column "Phone number" in line "1": Enter a valid phone number.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_attendee_email(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['attendee_email'] = 'csv:C'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert OrderPosition.objects.filter(attendee_email="schneider@example.org").exists()
    assert OrderPosition.objects.filter(attendee_email__isnull=True).count() == 1


@pytest.mark.django_db
@scopes_disabled()
def test_import_customer(user, event, item):
    event.organizer.settings.customer_accounts = True
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['customer'] = 'csv:C'
    c = event.organizer.customers.create(
        email="daniel@example.org",
    )
    event.organizer.customers.create(
        email="schneider@example.org",
    )
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert c.orders.count() == 1


@pytest.mark.django_db
@scopes_disabled()
def test_import_attendee_email_invalid(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['attendee_email'] = 'csv:A'
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Dieter" for column "Attendee e-mail address" in line "1": Enter a valid email address.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_product(user, event, item):
    i = Item.objects.create(
        event=event,
        name=LazyI18nString({'de': 'Foo', 'en': 'Bar'}),
        internal_name='Baz',
        default_price=23,
    )
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'csv:E'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert OrderPosition.objects.filter(item=i).count() == 3


@pytest.mark.django_db
@scopes_disabled()
def test_import_product_unknown(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'csv:A'
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Dieter" for column "Product" in line "1": No matching product was found.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_product_dupl(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'csv:E'
    Item.objects.create(
        event=event,
        name='Foo',
        default_price=23,
    )
    Item.objects.create(
        event=event,
        name='Foo',
        default_price=23,
    )
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Foo" for column "Product" in line "1": Multiple matching products were found.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_variation_required(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    item.variations.create(value='Default')
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "" for column "Product variation" in line "1": You need to select a variation for this product.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_variation_invalid(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['variation'] = 'csv:E'
    item.variations.create(value='Default')
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Foo" for column "Product variation" in line "1": No matching variation was found.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_variation_dynamic(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['variation'] = 'csv:E'
    v1 = item.variations.create(value='Foo')
    v2 = item.variations.create(value=LazyI18nString({'en': 'Bar'}))
    v3 = item.variations.create(value='Baz')
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    ).get()
    assert OrderPosition.objects.filter(variation=v1).count() == 1
    assert OrderPosition.objects.filter(variation=v2).count() == 1
    assert OrderPosition.objects.filter(variation=v3).count() == 1


@pytest.mark.django_db
@scopes_disabled()
def test_company(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['email'] = 'csv:C'
    settings['invoice_address_company'] = 'csv:C'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    ).get()
    assert event.orders.get(email='schneider@example.org').invoice_address.company == 'schneider@example.org'
    assert event.orders.get(email='schneider@example.org').invoice_address.is_business
    assert event.orders.get(email__isnull=True).invoice_address.company == ''
    assert not event.orders.get(email__isnull=True).invoice_address.is_business


@pytest.mark.django_db
@scopes_disabled()
def test_name_parts(user, event, item):
    event.settings.name_scheme = 'given_family'
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['email'] = 'csv:C'
    settings['invoice_address_name_given_name'] = 'csv:A'
    settings['invoice_address_name_family_name'] = 'csv:B'
    settings['attendee_name_given_name'] = 'csv:A'
    settings['attendee_name_family_name'] = 'csv:B'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    ).get()
    o = event.orders.get(email='schneider@example.org')
    assert o.invoice_address.name_parts == {
        '_scheme': 'given_family',
        'given_name': 'Dieter',
        'family_name': 'Schneider'
    }
    assert o.invoice_address.name_cached == 'Dieter Schneider'
    assert o.positions.first().attendee_name_parts == {
        '_scheme': 'given_family',
        'given_name': 'Dieter',
        'family_name': 'Schneider'
    }
    assert o.positions.first().attendee_name_cached == 'Dieter Schneider'


@pytest.mark.django_db
@scopes_disabled()
def test_import_country(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['invoice_address_country'] = 'csv:G'
    settings['email'] = 'csv:C'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert str(event.orders.get(email='schneider@example.org').invoice_address.country) == 'US'


@pytest.mark.django_db
@scopes_disabled()
def test_import_country_invalid(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['invoice_address_country'] = 'csv:A'
    settings['email'] = 'csv:C'
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Dieter" for column "Invoice address: Country" in line "1": Please enter a valid country code.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_street(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['invoice_address_street'] = 'csv:H'
    settings['attendee_street'] = 'csv:H'
    settings['email'] = 'csv:C'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert str(event.orders.get(email='schneider@example.org').invoice_address.street) == 'Texas'
    assert str(event.orders.get(email='schneider@example.org').positions.first().street) == 'Texas'


@pytest.mark.django_db
@scopes_disabled()
def test_import_state(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['invoice_address_country'] = 'csv:G'
    settings['invoice_address_state'] = 'csv:H'
    settings['attendee_country'] = 'csv:G'
    settings['attendee_state'] = 'csv:H'
    settings['email'] = 'csv:C'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert str(event.orders.get(email='schneider@example.org').invoice_address.country) == 'US'
    assert str(event.orders.get(email='schneider@example.org').invoice_address.country) == 'US'
    assert str(event.orders.get(email='schneider@example.org').positions.first().state) == 'TX'
    assert str(event.orders.get(email='schneider@example.org').positions.first().country) == 'US'


@pytest.mark.django_db
@scopes_disabled()
def test_import_state_invalid(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['invoice_address_country'] = 'static:AU'
    settings['invoice_address_state'] = 'csv:H'
    settings['email'] = 'csv:C'
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Texas" for column "Invoice address: State" in line "1": Please enter a valid state.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_saleschannel_invalid(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['sales_channel'] = 'csv:A'
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Dieter" for column "Sales channel" in line "1": Please enter a valid sales channel.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_locale_invalid(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['locale'] = 'static:de'  # not enabled on this event
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "de" for column "Order locale" in line "1": Please enter a valid language code.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_price_invalid(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['price'] = 'csv:A'
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Dieter" for column "Price" in line "1": You ' \
           'entered an invalid number.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_secret(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['secret'] = 'csv:A'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    ).get()
    assert OrderPosition.objects.filter(secret="Dieter").count() == 1


@pytest.mark.django_db
@scopes_disabled()
def test_import_secret_dupl(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['secret'] = 'csv:D'
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Test" for column "Ticket code" in line "2": You cannot assign a position ' \
           'secret that already exists.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_seat_required(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)

    event.seat_category_mappings.create(
        layout_category='Stalls', product=item
    )
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "" for column "Seat ID" in line "1": You need to select ' \
           'a specific seat.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_seat_blocked(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['seat'] = 'csv:D'

    event.seat_category_mappings.create(
        layout_category='Stalls', product=item
    )
    event.seats.create(seat_number="Test", product=item, seat_guid="Test", blocked=True)
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Test" for column "Seat ID" in line "1": The seat you selected has already ' \
           'been taken. Please select a different seat.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_seat_dbl(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['seat'] = 'csv:D'

    event.seat_category_mappings.create(
        layout_category='Stalls', product=item
    )
    event.seats.create(seat_number="Test", product=item, seat_guid="Test")
    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Test" for column "Seat ID" in line "2": The seat you selected has already ' \
           'been taken. Please select a different seat.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_seat(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['seat'] = 'csv:E'

    event.seat_category_mappings.create(
        layout_category='Stalls', product=item
    )
    s1 = event.seats.create(seat_number="Foo", product=item, seat_guid="Foo")
    s2 = event.seats.create(seat_number="Bar", product=item, seat_guid="Bar")
    s3 = event.seats.create(seat_number="Baz", product=item, seat_guid="Baz")
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    ).get()
    assert not s1.is_available()
    assert not s2.is_available()
    assert not s3.is_available()


@pytest.mark.django_db
@scopes_disabled()
def test_import_validity(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['valid_until'] = 'csv:J'

    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    ).get()
    assert OrderPosition.objects.first().valid_until.isoformat() == '2021-06-28T11:00:00+00:00'


@pytest.mark.django_db
@scopes_disabled()
def test_import_subevent_invalid(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    event.has_subevents = True
    event.save()
    event.subevents.create(name='Foo', date_from=now(), active=True)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['subevent'] = 'csv:E'

    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Bar" for column "Date" in line "2": No matching date was found.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_subevent_required(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    event.has_subevents = True
    event.save()
    settings['item'] = 'static:{}'.format(item.pk)

    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "" for column "Date" in line "1": You need to select a date.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_subevent_by_name(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    event.has_subevents = True
    event.save()
    s = event.subevents.create(name='Test', date_from=now(), active=True)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['subevent'] = 'csv:D'

    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    ).get()
    assert OrderPosition.objects.filter(subevent=s).count() == 3


@pytest.mark.django_db
@scopes_disabled()
def test_import_subevent_by_date(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    event.has_subevents = True
    event.save()
    event.settings.timezone = 'Europe/Berlin'
    s = event.subevents.create(name='Test', date_from=datetime.datetime(2021, 6, 28, 11, 0, 0, 0, tzinfo=event.timezone), active=True)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['subevent'] = 'csv:J'

    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    ).get()
    assert OrderPosition.objects.filter(subevent=s).count() == 3


@pytest.mark.django_db
@scopes_disabled()
def test_import_question_validate(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    q = event.questions.create(question='Foo', type=Question.TYPE_NUMBER)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['question_{}'.format(q.pk)] = 'csv:D'

    with pytest.raises(DataImportError) as excinfo:
        import_orders.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'Error while importing value "Test" for column "Question: Foo" in line "1": Invalid number input.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_question_valid(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    q = event.questions.create(question='Foo', type=Question.TYPE_CHOICE_MULTIPLE)
    o1 = q.options.create(answer='Foo', identifier='Foo')
    o2 = q.options.create(answer='Bar', identifier='Bar')
    settings['item'] = 'static:{}'.format(item.pk)
    settings['attendee_email'] = 'csv:C'
    settings['question_{}'.format(q.pk)] = 'csv:I'

    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    ).get()
    assert QuestionAnswer.objects.filter(question=q).count() == 3
    a1 = OrderPosition.objects.get(attendee_email='schneider@example.org').answers.first()
    assert a1.question == q
    assert list(a1.options.all()) == [o1]
    a3 = OrderPosition.objects.get(attendee_email__isnull=True).answers.first()
    assert a3.question == q
    assert set(a3.options.all()) == {o1, o2}

# TODO: validate question
