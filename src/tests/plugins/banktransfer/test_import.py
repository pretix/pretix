from datetime import timedelta
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, Item, Order, OrderFee, OrderPayment, OrderPosition, Organizer,
    Quota, Team, User,
)
from pretix.plugins.banktransfer.models import BankImportJob, BankTransaction
from pretix.plugins.banktransfer.tasks import process_banktransfers


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.paypal'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    t = Team.objects.create(organizer=event.organizer, can_view_orders=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)
    o1 = Order.objects.create(
        code='1Z3AS', event=event, email='admin@localhost',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23
    )
    o2 = Order.objects.create(
        code='6789Z', event=event,
        status=Order.STATUS_CANCELED,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23
    )
    Order.objects.create(
        code='GS89Z', event=event,
        status=Order.STATUS_CANCELED,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23
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
    for inp in doc.select("textarea"):
        data[inp.attrs['name']] = inp.text
    r = client.post('/control/event/dummy/dummy/banktransfer/import/', data)
    assert '/job/' in r['Location']


@pytest.fixture
def job(env):
    return BankImportJob.objects.create(event=env[0]).pk


@pytest.fixture
def orga_job(env):
    return BankImportJob.objects.create(organizer=env[0].organizer).pk


@pytest.mark.django_db
def test_mark_paid(env, job):
    djmail.outbox = []
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY1234S',
        'date': '2016-01-26',
        'amount': '23.00'
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == 'Payment received for your order: 1Z3AS'


@pytest.mark.django_db
def test_underpaid(env, job):
    djmail.outbox = []
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY1Z3AS',
        'date': '2016-01-26',
        'amount': '22.50'
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PENDING
    with scopes_disabled():
        p = env[2].payments.last()
        assert p.amount == Decimal('22.50')
        assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
        assert env[2].pending_sum == Decimal('0.50')

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == 'Your order received an incomplete payment: 1Z3AS'


@pytest.mark.django_db
def test_in_parts(env, job):
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY1Z3AS',
        'date': '2016-01-26',
        'amount': '10.00'
    }])
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY1Z3AS',
        'date': '2016-01-26',
        'amount': '13.00'
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID
    with scopes_disabled():
        assert env[2].payments.count() == 2
    assert env[2].pending_sum == Decimal('0.00')


@pytest.mark.django_db
def test_overpaid(env, job):
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY1Z3AS',
        'date': '2016-01-26',
        'amount': '23.50'
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID
    with scopes_disabled():
        p = env[2].payments.last()
        assert p.amount == Decimal('23.50')
        assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
        assert env[2].pending_sum == Decimal('-0.50')


@pytest.mark.django_db
def test_ignore_canceled(env, job):
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY6789Z',
        'date': '2016-01-26',
        'amount': '23.00'
    }])
    env[3].refresh_from_db()
    assert env[3].status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_autocorrection(env, job):
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY12345',
        'amount': '23.00',
        'date': '2016-01-26',
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_random_spaces(env, job):
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUM MY123 45NEXTLINE',
        'amount': '23.00',
        'date': '2016-01-26',
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_random_newlines(env, job):
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUM\nMY123\n 45NEXTLINE',
        'amount': '23.00',
        'date': '2016-01-26',
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_end_comma(env, job):
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY12345,NEXTLINE',
        'amount': '23.00',
        'date': '2016-01-26',
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_huge_amount(env, job):
    env[2].total = Decimal('23000.00')
    env[2].save()
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY12345',
        'amount': '23.000,00',
        'date': '2016-01-26',
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_mark_paid_organizer(env, orga_job):
    process_banktransfers(orga_job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY-1234S',
        'date': '2016-01-26',
        'amount': '23.00'
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_mark_paid_organizer_dash_in_slug(env, orga_job):
    env[0].slug = "foo-bar"
    env[0].save()
    process_banktransfers(orga_job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung FOO-BAR-1234S',
        'date': '2016-01-26',
        'amount': '23.00'
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_mark_paid_organizer_varying_order_code_length(env, orga_job):
    env[2].code = "123412341234"
    env[2].save()
    process_banktransfers(orga_job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY-123412341234',
        'date': '2016-01-26',
        'amount': '23.00'
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_mark_paid_organizer_weird_slug(env, orga_job):
    env[0].slug = 'du.m-y'
    env[0].save()
    process_banktransfers(orga_job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DU.M-Y-1234S',
        'date': '2016-01-26',
        'amount': '23.00'
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_wrong_event_organizer(env, orga_job):
    Event.objects.create(
        organizer=env[0].organizer, name='Wrong', slug='wrong',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    process_banktransfers(orga_job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung WRONG-1234S',
        'date': '2016-01-26',
        'amount': '23.00'
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_keep_unmatched(env, orga_job):
    process_banktransfers(orga_job, [{
        'payer': 'Karla Kundin',
        'reference': 'No useful reference',
        'date': '2016-01-26',
        'amount': '23.00'
    }])
    with scopes_disabled():
        job = BankImportJob.objects.last()
        t = job.transactions.last()
        assert t.state == BankTransaction.STATE_NOMATCH


@pytest.mark.django_db
def test_split_payment_success(env, orga_job):
    o4 = Order.objects.create(
        code='99999', event=env[0],
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=12
    )
    process_banktransfers(orga_job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellungen DUMMY-1Z3AS DUMMY-99999',
        'date': '2016-01-26',
        'amount': '35.00'
    }])
    with scopes_disabled():
        job = BankImportJob.objects.last()
        t = job.transactions.last()
        assert t.state == BankTransaction.STATE_VALID
        env[2].refresh_from_db()
        assert env[2].status == Order.STATUS_PAID
        assert env[2].payments.get().amount == Decimal('23.00')
        o4.refresh_from_db()
        assert o4.status == Order.STATUS_PAID
        assert o4.payments.get().amount == Decimal('12.00')


@pytest.mark.django_db
def test_split_payment_mismatch(env, orga_job):
    o4 = Order.objects.create(
        code='99999', event=env[0],
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=12
    )
    process_banktransfers(orga_job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellungen DUMMY-1Z3AS DUMMY-99999',
        'date': '2016-01-26',
        'amount': '36.00'
    }])
    with scopes_disabled():
        job = BankImportJob.objects.last()
        t = job.transactions.last()
        assert t.state == BankTransaction.STATE_NOMATCH
        env[2].refresh_from_db()
        assert env[2].status == Order.STATUS_PENDING
        o4.refresh_from_db()
        assert o4.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_import_very_long_csv_file(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.get('/control/event/dummy/dummy/banktransfer/import/')
    assert r.status_code == 200

    payload = """
Buchungstag;Valuta;Buchungstext;Auftraggeber / Empfänger;Verwendungszweck;Betrag in EUR;
09.04.2015;09.04.2015;SEPA-Überweisung;Karl Kunde;Bestellung 2015ABCDE;23,00;
09.04.2015;09.04.2015;SEPA-Überweisung;Karla Kundin;Bestellung DUMMYFGHIJ;42,00;
09.04.2015;09.04.2015;SEPA-Überweisung;Karla Kundin;Bestellung DUMMY1234S;42,00;
09.04.2015;09.04.2015;SEPA-Überweisung;Karla Kundin;Bestellung DUMMY1234S;23,00;
09.04.2015;09.04.2015;SEPA-Überweisung;Karla Kundin;Bestellung DUMMY6789Z;23,00;
09.04.2015;09.04.2015;SEPA-Überweisung;Karla Kundin;Bestellung DUMMY6789Z;23,00;
"""
    payload += "09.04.2015;09.04.2015;SEPA-Überweisung;Karla Kundin;Bestellung DUMMY6789Z;23,00;\n" * 1000

    file = SimpleUploadedFile('file.csv', payload.encode("utf-8"), content_type="text/csv")

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
    for inp in doc.select("textarea"):
        data[inp.attrs['name']] = inp.text
    r = client.post('/control/event/dummy/dummy/banktransfer/import/', data)
    assert '/job/' in r['Location']


@pytest.mark.django_db
def test_pending_paypal_drop_fee(env, job):
    with scopes_disabled():
        fee = env[2].fees.create(
            fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('2.00')
        )
        env[2].total += Decimal('2.00')
        env[2].save()
        p = env[2].payments.create(
            provider='paypal',
            state=OrderPayment.PAYMENT_STATE_PENDING,
            fee=fee,
            amount=env[2].total
        )
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY1234S',
        'date': '2016-01-26',
        'amount': '23.00'
    }])
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID
    with scopes_disabled():
        assert env[2].fees.count() == 0
    assert env[2].total == Decimal('23.00')
    p.refresh_from_db()
    assert p.state == OrderPayment.PAYMENT_STATE_CANCELED


@pytest.mark.django_db
def test_pending_paypal_replace_fee_included(env, job):
    with scopes_disabled():
        env[0].settings.set('payment_banktransfer__fee_abs', '1.00')
        fee = env[2].fees.create(
            fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('2.00')
        )
        env[2].total += Decimal('2.00')
        env[2].save()
        env[2].payments.create(
            provider='paypal',
            state=OrderPayment.PAYMENT_STATE_PENDING,
            fee=fee,
            amount=env[2].total
        )
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY1234S',
        'date': '2016-01-26',
        'amount': '24.00'
    }])
    with scopes_disabled():
        env[2].refresh_from_db()
        assert env[2].status == Order.STATUS_PAID
        assert env[2].fees.count() == 1
        assert env[2].fees.last().value == Decimal('1.00')
        assert env[2].total == Decimal('24.00')


@pytest.mark.django_db
def test_pending_paypal_replace_fee_missing(env, job):
    env[0].settings.set('payment_banktransfer__fee_abs', '1.00')
    with scopes_disabled():
        fee = env[2].fees.create(
            fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('2.00')
        )
        env[2].total += Decimal('2.00')
        env[2].save()
        env[2].payments.create(
            provider='paypal',
            state=OrderPayment.PAYMENT_STATE_PENDING,
            fee=fee,
            amount=env[2].total
        )
    process_banktransfers(job, [{
        'payer': 'Karla Kundin',
        'reference': 'Bestellung DUMMY1234S',
        'date': '2016-01-26',
        'amount': '23.00'
    }])
    env[2].refresh_from_db()
    with scopes_disabled():
        assert env[2].status == Order.STATUS_PENDING
        assert env[2].fees.count() == 1
        assert env[2].fees.last().value == Decimal('1.00')
        assert env[2].total == Decimal('24.00')
