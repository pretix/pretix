import json
import os
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import (
    CachedCombinedTicket, CachedTicket, Event, InvoiceAddress, Order,
    OrderPayment, OrderPosition, Organizer, QuestionAnswer,
)
from pretix.base.services.invoices import generate_invoice, invoice_pdf_task
from pretix.base.services.tickets import generate
from pretix.base.shredder import (
    AttendeeInfoShredder, CachedTicketShredder, EmailAddressShredder,
    InvoiceAddressShredder, InvoiceShredder, PaymentInfoShredder,
    QuestionAnswerShredder, WaitingListShredder, shred_constraints,
)


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.ticketoutputpdf'
    )
    with scope(organizer=o):
        yield event


@pytest.fixture
def item(event):
    return event.items.create(
        name='Early-bird ticket',
        category=None, default_price=23,
        admission=True
    )


@pytest.fixture
def order(event, item):
    o = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=14, locale='en'
    )
    event.settings.set('attendee_names_asked', True)
    event.settings.set('locales', ['en', 'de'])
    OrderPosition.objects.create(
        order=o,
        item=item,
        variation=None,
        price=Decimal("14"),
        attendee_name_parts={'full_name': "Peter", "_scheme": "full"},
        attendee_email="foo@example.org",
        company='Foobar',
    )
    return o


@pytest.fixture
def question(event, item):
    q = event.questions.create(question="T-Shirt size", type="C", identifier="ABC")
    q.items.add(item)
    q.options.create(answer="XL", identifier="LVETRWVU")
    return q


@pytest.mark.django_db
def test_email_shredder(event, order):
    l1 = order.log_action(
        'pretix.event.order.email.expired',
        data={
            'recipient': 'dummy@dummy.test',
            'message': 'Hello Peter@,',
            'subject': 'Foo'
        }
    )
    l2 = order.log_action(
        'pretix.event.order.contact.changed',
        data={
            'old_email': 'dummy@dummy.test',
            'new_email': 'foo@bar.com',
        }
    )

    s = EmailAddressShredder(event)
    f = list(s.generate_files())
    assert json.loads(f[0][2]) == {
        order.code: 'dummy@dummy.test'
    }
    assert json.loads(f[1][2]) == {
        '{}-{}'.format(order.code, 1): 'foo@example.org'
    }
    s.shred_data()
    order.refresh_from_db()
    assert order.email is None
    assert order.positions.first().attendee_email is None
    l1.refresh_from_db()
    assert '@' not in l1.data
    assert 'Foo' not in l1.data
    l2.refresh_from_db()
    assert '@' not in l2.data


@pytest.mark.django_db
def test_waitinglist_shredder(event, item):
    q = event.quotas.create(size=5)
    q.items.add(item)
    wle = event.waitinglistentries.create(
        item=item, email='foo@example.org'
    )
    wle.send_voucher()
    assert '@' in wle.voucher.comment
    assert '@' in wle.voucher.all_logentries().last().data
    s = WaitingListShredder(event)
    f = list(s.generate_files())
    assert json.loads(f[0][2]) == [
        {
            'id': wle.pk,
            'item': item.pk,
            'variation': None,
            'subevent': None,
            'voucher': wle.voucher.pk,
            'created': wle.created.isoformat().replace('+00:00', 'Z'),
            'locale': 'en',
            'priority': 0,
            'email': 'foo@example.org'
        }
    ]
    s.shred_data()
    wle.refresh_from_db()
    wle.voucher.refresh_from_db()
    assert '@' not in wle.email
    assert '@' not in wle.voucher.comment
    assert '@' not in wle.voucher.all_logentries().last().data


@pytest.mark.django_db
def test_attendee_name_shredder(event, order):
    l1 = order.log_action(
        'pretix.event.order.modified',
        data={
            "data": [{"attendee_name": "Peter", "question_1": "Test", "company": "Foobar"}],
            "invoice_data": {"name": "Foo"}
        }
    )

    s = AttendeeInfoShredder(event)
    f = list(s.generate_files())
    assert json.loads(f[0][2]) == {
        '{}-{}'.format(order.code, 1): {
            'name': 'Peter',
            'company': 'Foobar',
            'street': None,
            'zipcode': None,
            'city': None,
            'country': None,
            'state': None
        }
    }
    s.shred_data()
    order.refresh_from_db()
    assert not order.positions.first().attendee_name
    l1.refresh_from_db()
    assert 'Hans' not in l1.data
    assert 'Foo' in l1.data
    assert 'Foobar' not in l1.data
    assert 'Test' in l1.data


@pytest.mark.django_db
def test_invoice_address_shredder(event, order):
    l1 = order.log_action(
        'pretix.event.order.modified',
        data={
            "data": [{"attendee_name": "Hans", "question_1": "Test"}],
            "invoice_data": {"name": "Peter", "country": "DE", "is_business": False, "internal_reference": "",
                             "state": "",
                             "company": "ACME", "street": "Sesam Street", "city": "Sample City", "zipcode": "12345"}
        }
    )
    ia = InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street',
                                       zipcode='12345', city='London', country='UK',
                                       order=order)
    s = InvoiceAddressShredder(event)
    f = list(s.generate_files())
    assert json.loads(f[0][2]) == {
        order.code: {
            'city': 'London',
            'company': 'Acme Company',
            'country': 'UK',
            'internal_reference': '',
            'is_business': False,
            'last_modified': ia.last_modified.isoformat().replace('+00:00', 'Z'),
            'name': '',
            'name_parts': {},
            'state': '',
            'street': '221B Baker Street',
            'vat_id': '',
            'vat_id_validated': False,
            'zipcode': '12345'
        }
    }
    s.shred_data()
    order.refresh_from_db()
    assert not InvoiceAddress.objects.filter(order=order).exists()
    l1.refresh_from_db()
    assert l1.parsed_data == {
        "data": [{"attendee_name": "Hans", "question_1": "Test"}],
        "invoice_data": {"name": "█", "country": "█", "is_business": False, "internal_reference": "", "company": "█",
                         "street": "█", "city": "█", "zipcode": "█", "state": ""}
    }


@pytest.mark.django_db
def test_question_answer_shredder(event, order, question):
    opt = question.options.first()
    l1 = order.log_action(
        'pretix.event.order.modified',
        data={
            "data": [
                {
                    "attendee_name": "Hans",
                    "question_%d" % question.pk: [{"id": opt.pk, "type": "QuestionOption"}]
                }
            ],
        }
    )
    qa = QuestionAnswer.objects.create(
        orderposition=order.positions.first(),
        question=question,
        answer='S'
    )
    qa.file.save('foo.pdf', ContentFile('foo'))
    fname = qa.file.path
    assert os.path.exists(fname)
    qa.options.add(opt)
    s = QuestionAnswerShredder(event)
    f = list(s.generate_files())
    assert json.loads(f[0][2]) == {
        '{}-1'.format(order.code): [{
            'question': question.pk,
            'answer': 'S',
            'question_identifier': question.identifier,
            'options': [opt.pk],
            'option_identifiers': [opt.identifier],
        }]
    }
    s.shred_data()
    order.refresh_from_db()
    assert not os.path.exists(fname)
    assert not QuestionAnswer.objects.filter(pk=qa.pk).exists()
    l1.refresh_from_db()
    assert l1.parsed_data == {
        "data": [{"attendee_name": "Hans", "question_%d" % question.pk: "█"}],
    }


@pytest.mark.django_db
def test_invoice_shredder(event, order):
    InvoiceAddress.objects.create(company='Acme Company', street='221B Baker Street',
                                  zipcode='12345', city='London', country='UK',
                                  order=order)
    inv = generate_invoice(order)
    invoice_pdf_task.apply(args=(inv.pk,))
    inv.refresh_from_db()
    assert inv.invoice_to == "Acme Company\n221B Baker Street\n12345 London"
    assert inv.file
    fname = inv.file.path
    assert os.path.exists(fname)
    s = InvoiceShredder(event)
    f = list(s.generate_files())
    assert len(f) == 1
    s.shred_data()
    inv.refresh_from_db()

    assert "Acme" not in inv.invoice_to
    assert "icket" not in inv.lines.first().description
    assert not inv.file
    assert not os.path.exists(fname)


@pytest.mark.django_db
def test_cached_tickets(event, order):
    generate('orderposition', order.positions.first().pk, 'pdf')
    generate('order', order.pk, 'pdf')

    ct = CachedTicket.objects.get(order_position=order.positions.first(), provider='pdf')
    cct = CachedCombinedTicket.objects.get(order=order, provider='pdf')
    assert ct.file
    assert cct.file
    ct_fname = ct.file.path
    cct_fname = cct.file.path
    assert os.path.exists(ct_fname)
    assert os.path.exists(cct_fname)
    s = CachedTicketShredder(event)
    assert s.generate_files() is None
    s.shred_data()

    assert not CachedTicket.objects.filter(order_position=order.positions.first(), provider='pdf').exists()
    assert not CachedCombinedTicket.objects.filter(order=order, provider='pdf').exists()
    assert not os.path.exists(ct_fname)
    assert not os.path.exists(cct_fname)


@pytest.mark.django_db
def test_payment_info_shredder(event, order):
    order.payments.create(info=json.dumps({
        'reference': 'Verwendungszweck 1',
        'date': '2018-05-01',
        'payer': 'Hans',
        'trans_id': 12
    }), provider='banktransfer', amount=order.total, state=OrderPayment.PAYMENT_STATE_PENDING)
    order.save()

    s = PaymentInfoShredder(event)
    assert s.generate_files() is None
    s.shred_data()

    order.refresh_from_db()
    assert order.payments.first().info_data == {
        '_shredded': True,
        'reference': '█',
        'date': '2018-05-01',
        'payer': '█',
        'trans_id': 12
    }


@pytest.mark.django_db
def test_shred_constraint_offline(event):
    event.live = True
    event.date_from = now() - timedelta(days=365)
    assert shred_constraints(event)


@pytest.mark.django_db
def test_shred_constraint_60_days(event):
    event.live = False
    event.date_from = now() - timedelta(days=62)
    event.date_to = now() - timedelta(days=62)
    assert shred_constraints(event) is None
    event.date_from = now() - timedelta(days=52)
    event.date_to = now() - timedelta(days=52)
    assert shred_constraints(event)
    event.date_from = now() - timedelta(days=62)
    event.date_to = now() - timedelta(days=52)
    assert shred_constraints(event)


@pytest.mark.django_db
def test_shred_constraint_60_days_subevents(event):
    event.has_subevents = True
    event.live = False

    event.subevents.create(
        date_from=now() - timedelta(days=62),
        date_to=now() - timedelta(days=62)
    )
    assert shred_constraints(event) is None
    event.subevents.create(
        date_from=now() - timedelta(days=62),
        date_to=now() - timedelta(days=52)
    )
    assert shred_constraints(event)
