import csv
from _decimal import Decimal
from io import StringIO

import pytest
from django.core.files.base import ContentFile
from django.utils.timezone import now
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString

from pretix.base.models import (
    CachedFile, Event, Item, Order, OrderPayment, OrderPosition, Organizer,
    User,
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
        },
        {
            'A': 'Anke',
            'B': 'Müller',
            'C': '',
            'D': 'Test',
            'E': 'Baz',
            'F': '0.00',
            'G': 'AU',
            'H': '',
        },
    ]
    f = StringIO()
    w = csv.DictWriter(f, ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'])
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
def test_import_state(user, event, item):
    settings = dict(DEFAULT_SETTINGS)
    settings['item'] = 'static:{}'.format(item.pk)
    settings['invoice_address_country'] = 'csv:G'
    settings['invoice_address_state'] = 'csv:H'
    settings['email'] = 'csv:C'
    import_orders.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert str(event.orders.get(email='schneider@example.org').invoice_address.country) == 'US'
    assert str(event.orders.get(email='schneider@example.org').invoice_address.state) == 'TX'


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


# TODO: require/validate subevent
# TODO: validate seat
# TODO: validate question
