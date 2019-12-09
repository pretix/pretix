import csv
from io import StringIO

import pytest
from django.core.files.base import ContentFile
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import CachedFile, Event, Item, Organizer, User
from pretix.base.services.orderimport import import_orders


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
def inputfile():
    d = [
        {
            'A': 'Dieter',
            'B': 'Schneider',
            'C': 'schneider@example.org',
            'D': 'Test',
            'E': 'Foo'
        },
        {
            'A': 'Daniel',
            'B': 'Wulf',
            'C': 'daniel@example.org',
            'D': 'Test',
            'E': 'Bar'
        },
        {
            'A': 'Anke',
            'B': 'Müller',
            'C': 'anke@example.net',
            'D': 'Test',
            'E': 'Baz'
        },
    ]
    f = StringIO()
    w = csv.DictWriter(f, ['A', 'B', 'C', 'D', 'E'])
    w.writeheader()
    w.writerows(d)
    f.seek(0)
    c = CachedFile.objects.create(type="text/csv", filename="input.csv")
    c.file.save("input.csv", ContentFile(f.read()))
    return c


@pytest.mark.django_db
@scopes_disabled()
def test_import_simple(client, event, inputfile, item):
    settings = {
        'orders': 'many',
        'testmode': False,
        'status': 'paid',
        'item': 'static:{}'.format(item.pk),
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
    import_orders.apply(
        args=(event.pk, inputfile.id, settings, 'en', User.objects.create_user('test@localhost', 'test').pk))
    assert event.orders.count() == 3
