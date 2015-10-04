from datetime import timedelta

import pytest
from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now

from pretix.base.models import (
    Event, EventPermission, Item, Order, OrderPosition, Organizer, Quota, User,
)


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    EventPermission.objects.create(user=user, event=event)
    o1 = Order.objects.create(
        code='1234S', event=event,
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, payment_provider='banktransfer'
    )
    o2 = Order.objects.create(
        code='6789Z', event=event,
        status=Order.STATUS_CANCELLED,
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

""".encode("utf-8"), content_type="text/csv")

    r = client.post('/control/event/dummy/dummy/banktransfer/import/', {
        'file': file
    })
    doc = BeautifulSoup(r.content)
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
    doc = BeautifulSoup(r.content)
    assert r.status_code == 200
    assert len(doc.select("form table tbody tr")) == 5
    trs = doc.select("form table tbody tr")
    assert trs[0].select("td")[0].text == "09.04.2015"
    assert trs[0].select("td")[1].text == "Bestellung 2015ABCDE"
    assert trs[0].select("td")[2].text == "23.00"
    assert trs[0].select("td")[3].text == "Karl Kunde"
    assert trs[0].select("td")[5].text == "No order code detected"
    assert trs[1].select("td")[0].text == "09.04.2015"
    assert trs[1].select("td")[1].text == "Bestellung DUMMYFGHIJ"
    assert trs[1].select("td")[2].text == "42.00"
    assert trs[1].select("td")[3].text == "Karla Kundin"
    assert trs[1].select("td")[5].text == "Unknown order code detected"
    assert trs[2].select("td")[0].text == "09.04.2015"
    assert trs[2].select("td")[1].text == "Bestellung DUMMY1234S"
    assert trs[2].select("td")[2].text == "42.00"
    assert trs[2].select("td")[3].text == "Karla Kundin"
    assert trs[2].select("td")[5].text == "Found wrong amount. Expected: 23.00"
    assert trs[3].select("td")[0].text == "09.04.2015"
    assert trs[3].select("td")[1].text == "Bestellung DUMMY1234S"
    assert trs[3].select("td")[2].text == "23.00"
    assert trs[3].select("td")[3].text == "Karla Kundin"
    assert trs[3].select("td")[5].text == "Valid payment"
    assert trs[4].select("td")[0].text == "09.04.2015"
    assert trs[4].select("td")[1].text == "Bestellung DUMMY6789Z"
    assert trs[4].select("td")[2].text == "23.00"
    assert trs[4].select("td")[3].text == "Karla Kundin"
    assert trs[4].select("td")[5].text == "Order has been cancelled"

    data = {}
    for inp in doc.select("form input"):
        data[inp.attrs['name']] = inp.attrs['value']
    client.post('/control/event/dummy/dummy/banktransfer/import/', data)

    assert Order.objects.current.get(identity=env[2].identity).status == Order.STATUS_PAID
    assert Order.objects.current.get(identity=env[3].identity).status == Order.STATUS_CANCELLED
