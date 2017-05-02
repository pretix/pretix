from datetime import timedelta
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now

from pretix.base.models import (
    Event, Item, Order, OrderPosition, Organizer, Quota, Team, User,
)
from pretix.plugins.banktransfer.models import BankImportJob
from pretix.plugins.banktransfer.tasks import process_banktransfers


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    t = Team.objects.create(organizer=event.organizer, can_view_orders=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)
    o1 = Order.objects.create(
        code='1Z3AS', event=event,
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, payment_provider='banktransfer'
    )
    o2 = Order.objects.create(
        code='6789Z', event=event,
        status=Order.STATUS_CANCELED,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, payment_provider='banktransfer'
    )
    Order.objects.create(
        code='GS89Z', event=event,
        status=Order.STATUS_CANCELED,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, payment_provider='banktransfer'
    )
    quota = Quota.objects.create(name="Test", size=2, event=event)
    item1 = Item.objects.create(event=event, name="Ticket", default_price=23)
    quota.items.add(item1)
    OrderPosition.objects.create(order=o1, item=item1, variation=None, price=23)
    return event, user, o1, o2


@pytest.mark.django_db
def test_import_csv_file(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.get('/control/event/dummy/dummy/banktransfer/import/')
    assert r.status_code == 200

    file = SimpleUploadedFile('file.csv', """
Buchungstag;Valuta;Buchungstext;Auftraggeber / Empfänger;Verwendungszweck;Betrag in EUR;
09.04.2015;09.04.2015;SEPA-Überweisung;Karl Kunde;Bestellung 2015ABCDE;23,00;
09.04.2015;09.04.2015;SEPA-Überweisung;Karla Kundin;Bestellung DUMMYFGHIJ;42,00;
09.04.2015;09.04.2015;SEPA-Überweisung;Karla Kundin;Bestellung DUMMY1234S;42,00;
09.04.2015;09.04.2015;SEPA-Überweisung;Karla Kundin;Bestellung DUMMY1234S;23,00;
09.04.2015;09.04.2015;SEPA-Überweisung;Karla Kundin;Bestellung DUMMY6789Z;23,00;
09.04.2015;09.04.2015;SEPA-Überweisung;Karla Kundin;Bestellung DUMMY65892;23,00;

""".encode("utf-8"), content_type="text/csv")

    r = client.post('/control/event/dummy/dummy/banktransfer/import/', {
        'file': file
    })
    doc = BeautifulSoup(r.content, "lxml")
    assert r.status_code == 200
    assert len(doc.select("input[name=date]")) > 0
    data = {
        'payer': [3],
        'reference': [4],
        'date': 1,
        'amount': 5,
        'cols': 7
    }
    for inp in doc.select("input[type=hidden]"):
        data[inp.attrs['name']] = inp.attrs['value']
    r = client.post('/control/event/dummy/dummy/banktransfer/import/', data)
    assert '/job/' in r['Location']


@pytest.fixture
def job(env):
    return BankImportJob.objects.create(event=env[0]).pk


@pytest.mark.django_db
def test_mark_paid(env, job):
    process_banktransfers(env[0].pk, job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY1234S',
        'date': '2016-01-26',
        'amount': '23.00'
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_check_amount(env, job):
    process_banktransfers(env[0].pk, job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY1Z3AS',
        'date': '2016-01-26',
        'amount': '23.50'
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_ignore_canceled(env, job):
    process_banktransfers(env[0].pk, job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY6789Z',
        'date': '2016-01-26',
        'amount': '23.00'
    }])
    env[3].refresh_from_db()
    assert env[3].status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_autocorrection(env, job):
    process_banktransfers(env[0].pk, job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY12345',
        'amount': '23.00',
        'date': '2016-01-26',
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_huge_amount(env, job):
    env[2].total = Decimal('23000.00')
    env[2].save()
    process_banktransfers(env[0].pk, job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY12345',
        'amount': '23.000,00',
        'date': '2016-01-26',
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID
