import copy
import datetime
import json
from decimal import Decimal
from unittest import mock

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_countries.fields import Country
from pytz import UTC
from stripe.error import APIConnectionError
from tests.plugins.stripe.test_provider import MockedCharge

from pretix.base.models import InvoiceAddress, Order, OrderPosition, Question
from pretix.base.models.orders import (
    CartPosition, OrderFee, OrderPayment, OrderRefund,
)
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice,
)


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def item2(event2):
    return event2.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def taxrule(event):
    return event.tax_rules.create(rate=Decimal('19.00'))


@pytest.fixture
def question(event, item):
    q = event.questions.create(question="T-Shirt size", type="S", identifier="ABC")
    q.items.add(item)
    q.options.create(answer="XL", identifier="LVETRWVU")
    return q


@pytest.fixture
def question2(event2, item2):
    q = event2.questions.create(question="T-Shirt size", type="S", identifier="ABC")
    q.items.add(item2)
    return q


@pytest.fixture
def quota(event, item):
    q = event.quotas.create(name="Budget Quota", size=200)
    q.items.add(item)
    return q


@pytest.fixture
def order(event, item, taxrule, question):
    testtime = datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC)
    event.plugins += ",pretix.plugins.stripe"
    event.save()

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, secret="k24fiuwvu8kxz3y1",
            datetime=datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC),
            expires=datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=UTC),
            total=23, locale='en'
        )
        p1 = o.payments.create(
            provider='stripe',
            state='refunded',
            amount=Decimal('23.00'),
            payment_date=testtime,
        )
        o.refunds.create(
            provider='stripe',
            state='done',
            source='admin',
            amount=Decimal('23.00'),
            execution_date=testtime,
            payment=p1,
        )
        o.payments.create(
            provider='banktransfer',
            state='pending',
            amount=Decimal('23.00'),
        )
        o.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.25'), tax_rate=Decimal('19.00'),
                      tax_value=Decimal('0.05'), tax_rule=taxrule)
        InvoiceAddress.objects.create(order=o, company="Sample company", country=Country('NZ'))
        op = OrderPosition.objects.create(
            order=o,
            item=item,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={"full_name": "Peter"},
            secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
            pseudonymization_id="ABCDEFGHKL",
        )
        op.answers.create(question=question, answer='S')
        return o


TEST_ORDERPOSITION_RES = {
    "id": 1,
    "order": "FOO",
    "positionid": 1,
    "item": 1,
    "variation": None,
    "price": "23.00",
    "attendee_name_parts": {"full_name": "Peter"},
    "attendee_name": "Peter",
    "attendee_email": None,
    "voucher": None,
    "tax_rate": "0.00",
    "tax_value": "0.00",
    "tax_rule": None,
    "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
    "addon_to": None,
    "pseudonymization_id": "ABCDEFGHKL",
    "checkins": [],
    "downloads": [],
    "answers": [
        {
            "question": 1,
            "answer": "S",
            "question_identifier": "ABC",
            "options": [],
            "option_identifiers": []
        }
    ],
    "subevent": None
}
TEST_PAYMENTS_RES = [
    {
        "local_id": 1,
        "created": "2017-12-01T10:00:00Z",
        "payment_date": "2017-12-01T10:00:00Z",
        "provider": "stripe",
        "state": "refunded",
        "amount": "23.00"
    },
    {
        "local_id": 2,
        "created": "2017-12-01T10:00:00Z",
        "payment_date": None,
        "provider": "banktransfer",
        "state": "pending",
        "amount": "23.00"
    }
]
TEST_REFUNDS_RES = [
    {
        "local_id": 1,
        "payment": 1,
        "source": "admin",
        "created": "2017-12-01T10:00:00Z",
        "execution_date": "2017-12-01T10:00:00Z",
        "provider": "stripe",
        "state": "done",
        "amount": "23.00"
    },
]
TEST_ORDER_RES = {
    "code": "FOO",
    "status": "n",
    "secret": "k24fiuwvu8kxz3y1",
    "email": "dummy@dummy.test",
    "locale": "en",
    "datetime": "2017-12-01T10:00:00Z",
    "expires": "2017-12-10T10:00:00Z",
    "payment_date": "2017-12-01",
    "fees": [
        {
            "fee_type": "payment",
            "value": "0.25",
            "description": "",
            "internal_type": "",
            "tax_rate": "19.00",
            "tax_value": "0.05"
        }
    ],
    "payment_provider": "banktransfer",
    "total": "23.00",
    "comment": "",
    "checkin_attention": False,
    "invoice_address": {
        "last_modified": "2017-12-01T10:00:00Z",
        "is_business": False,
        "company": "Sample company",
        "name": "",
        "street": "",
        "zipcode": "",
        "city": "",
        "country": "NZ",
        "internal_reference": "",
        "vat_id": "",
        "vat_id_validated": False
    },
    "require_approval": False,
    "positions": [TEST_ORDERPOSITION_RES],
    "downloads": [],
    "payments": TEST_PAYMENTS_RES,
    "refunds": TEST_REFUNDS_RES,
}


@pytest.mark.django_db
def test_order_list(token_client, organizer, event, order, item, taxrule, question):
    res = dict(TEST_ORDER_RES)
    res["positions"][0]["id"] = order.positions.first().pk
    res["positions"][0]["item"] = item.pk
    res["positions"][0]["answers"][0]["question"] = question.pk
    res["last_modified"] = order.last_modified.isoformat().replace('+00:00', 'Z')
    res["fees"][0]["tax_rule"] = taxrule.pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?code=FOO'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?code=BAR'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?status=n'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?status=p'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orders/?email=dummy@dummy.test'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orders/?email=foo@example.org'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?locale=en'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?locale=de'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?modified_since={}'.format(
        organizer.slug, event.slug,
        (order.last_modified - datetime.timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
    ))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?modified_since={}'.format(
        organizer.slug, event.slug, order.last_modified.isoformat().replace('+00:00', 'Z')
    ))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?modified_since={}'.format(
        organizer.slug, event.slug,
        (order.last_modified + datetime.timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
    ))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_order_detail(token_client, organizer, event, order, item, taxrule, question):
    res = dict(TEST_ORDER_RES)
    res["positions"][0]["id"] = order.positions.first().pk
    res["positions"][0]["item"] = item.pk
    res["fees"][0]["tax_rule"] = taxrule.pk
    res["positions"][0]["answers"][0]["question"] = question.pk
    res["last_modified"] = order.last_modified.isoformat().replace('+00:00', 'Z')
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/'.format(organizer.slug, event.slug,
                                                                                order.code))
    assert resp.status_code == 200
    assert res == resp.data

    order.status = 'p'
    order.save()
    event.settings.ticketoutput_pdf__enabled = True
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/'.format(organizer.slug, event.slug,
                                                                                order.code))
    assert len(resp.data['downloads']) == 1
    assert len(resp.data['positions'][0]['downloads']) == 1

    order.status = 'n'
    order.save()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/'.format(organizer.slug, event.slug,
                                                                                order.code))
    assert len(resp.data['downloads']) == 0
    assert len(resp.data['positions'][0]['downloads']) == 0

    event.settings.ticket_download_pending = True
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/'.format(organizer.slug, event.slug,
                                                                                order.code))
    assert len(resp.data['downloads']) == 1
    assert len(resp.data['positions'][0]['downloads']) == 1


@pytest.mark.django_db
def test_payment_list(token_client, organizer, event, order):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/payments/'.format(organizer.slug, event.slug,
                                                                                         order.code))
    assert resp.status_code == 200
    assert TEST_PAYMENTS_RES == resp.data['results']


@pytest.mark.django_db
def test_payment_detail(token_client, organizer, event, order):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/payments/1/'.format(organizer.slug, event.slug,
                                                                                           order.code))
    assert resp.status_code == 200
    assert TEST_PAYMENTS_RES[0] == resp.data


@pytest.mark.django_db
def test_payment_confirm(token_client, organizer, event, order):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/confirm/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'force': True})
    p = order.payments.get(local_id=2)
    assert resp.status_code == 200
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/confirm/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'force': True})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_payment_cancel(token_client, organizer, event, order):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/cancel/'.format(
        organizer.slug, event.slug, order.code
    ))
    p = order.payments.get(local_id=2)
    assert resp.status_code == 200
    assert p.state == OrderPayment.PAYMENT_STATE_CANCELED

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/cancel/'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 400


@pytest.mark.django_db
def test_payment_refund_fail(token_client, organizer, event, order, monkeypatch):
    order.payments.last().confirm()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'amount': '25.00',
        'mark_refunded': False
    })
    assert resp.status_code == 400
    assert resp.data == {'amount': ['Invalid refund amount, only 23.00 are available to refund.']}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'amount': '20.00',
        'mark_refunded': False
    })
    assert resp.status_code == 400
    assert resp.data == {'amount': ['Partial refund not available for this payment method.']}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'mark_refunded': False
    })
    assert resp.status_code == 400
    assert resp.data == {'amount': ['Full refund not available for this payment method.']}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'amount': '23.00',
        'mark_refunded': False
    })
    assert resp.status_code == 400
    assert resp.data == {'amount': ['Full refund not available for this payment method.']}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/1/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'amount': '23.00',
        'mark_refunded': False
    })
    assert resp.status_code == 400
    assert resp.data == {'detail': 'Invalid state of payment.'}


@pytest.mark.django_db
def test_payment_refund_success(token_client, organizer, event, order, monkeypatch):
    def charge_retr(*args, **kwargs):
        def refund_create(amount):
            r = MockedCharge()
            r.id = 'foo'
            r.status = 'succeeded'
            return r

        c = MockedCharge()
        c.refunds.create = refund_create
        return c

    p1 = order.payments.create(
        provider='stripe',
        state='confirmed',
        amount=Decimal('23.00'),
        payment_date=order.datetime,
        info=json.dumps({
            'id': 'ch_123345345'
        })
    )
    monkeypatch.setattr("stripe.Charge.retrieve", charge_retr)
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/{}/refund/'.format(
        organizer.slug, event.slug, order.code, p1.local_id
    ), format='json', data={
        'amount': '23.00',
        'mark_refunded': False,
    })
    assert resp.status_code == 200
    r = order.refunds.get(local_id=resp.data['local_id'])
    assert r.provider == "stripe"
    assert r.state == OrderRefund.REFUND_STATE_DONE
    assert r.source == OrderRefund.REFUND_SOURCE_ADMIN


@pytest.mark.django_db
def test_payment_refund_unavailable(token_client, organizer, event, order, monkeypatch):
    def charge_retr(*args, **kwargs):
        def refund_create(amount):
            raise APIConnectionError(message='Foo')

        c = MockedCharge()
        c.refunds.create = refund_create
        return c

    p1 = order.payments.create(
        provider='stripe',
        state='confirmed',
        amount=Decimal('23.00'),
        payment_date=order.datetime,
        info=json.dumps({
            'id': 'ch_123345345'
        })
    )
    monkeypatch.setattr("stripe.Charge.retrieve", charge_retr)
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/{}/refund/'.format(
        organizer.slug, event.slug, order.code, p1.local_id
    ), format='json', data={
        'amount': '23.00',
        'mark_refunded': False,
    })
    assert resp.status_code == 400
    assert resp.data == {'detail': 'External error: We had trouble communicating with Stripe. Please try again and contact support if the problem persists.'}
    r = order.refunds.last()
    assert r.provider == "stripe"
    assert r.state == OrderRefund.REFUND_STATE_FAILED
    assert r.source == OrderRefund.REFUND_SOURCE_ADMIN


@pytest.mark.django_db
def test_refund_list(token_client, organizer, event, order):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(organizer.slug, event.slug,
                                                                                        order.code))
    assert resp.status_code == 200
    assert TEST_REFUNDS_RES == resp.data['results']


@pytest.mark.django_db
def test_refund_detail(token_client, organizer, event, order):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/'.format(organizer.slug, event.slug,
                                                                                          order.code))
    assert resp.status_code == 200
    assert TEST_REFUNDS_RES[0] == resp.data


@pytest.mark.django_db
def test_refund_done(token_client, organizer, event, order):
    r = order.refunds.get(local_id=1)
    r.state = 'transit'
    r.save()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/done/'.format(
        organizer.slug, event.slug, order.code
    ))
    r = order.refunds.get(local_id=1)
    assert resp.status_code == 200
    assert r.state == OrderRefund.REFUND_STATE_DONE

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/done/'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 400


@pytest.mark.django_db
def test_refund_process_mark_refunded(token_client, organizer, event, order):
    p = order.payments.get(local_id=1)
    p.create_external_refund()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/2/process/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'mark_refunded': True})
    r = order.refunds.get(local_id=1)
    assert resp.status_code == 200
    assert r.state == OrderRefund.REFUND_STATE_DONE
    order.refresh_from_db()
    assert order.status == Order.STATUS_REFUNDED

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/2/process/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'mark_refunded': True})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_refund_process_mark_pending(token_client, organizer, event, order):
    p = order.payments.get(local_id=1)
    p.create_external_refund()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/2/process/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'mark_refunded': False})
    r = order.refunds.get(local_id=1)
    assert resp.status_code == 200
    assert r.state == OrderRefund.REFUND_STATE_DONE
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_refund_cancel(token_client, organizer, event, order):
    r = order.refunds.get(local_id=1)
    r.state = 'transit'
    r.save()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/cancel/'.format(
        organizer.slug, event.slug, order.code
    ))
    r = order.refunds.get(local_id=1)
    assert resp.status_code == 200
    assert r.state == OrderRefund.REFUND_STATE_CANCELED

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/cancel/'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 400


@pytest.mark.django_db
def test_orderposition_list(token_client, organizer, event, order, item, subevent, subevent2, question):
    i2 = copy.copy(item)
    i2.pk = None
    i2.save()
    var = item.variations.create(value="Children")
    var2 = item.variations.create(value="Children")
    res = dict(TEST_ORDERPOSITION_RES)
    op = order.positions.first()
    op.variation = var
    op.save()
    res["id"] = op.pk
    res["item"] = item.pk
    res["variation"] = var.pk
    res["answers"][0]["question"] = question.pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?order__status=n'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?order__status=p'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?item={}'.format(organizer.slug, event.slug, item.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?item__in={},{}'.format(
            organizer.slug, event.slug, item.pk, i2.pk
        ))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?item={}'.format(organizer.slug, event.slug, i2.pk))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?variation={}'.format(organizer.slug, event.slug, var.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?variation={}'.format(organizer.slug, event.slug, var2.pk))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?attendee_name=Peter'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?attendee_name=peter'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?attendee_name=Mark'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?secret=z3fsn8jyufm5kpk768q69gkbyr5f4h6w'.format(
            organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?secret=abc123'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?pseudonymization_id=ABCDEFGHKL'.format(
            organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?pseudonymization_id=FOO'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?search=FO'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?search=z3fsn8j'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?search=Peter'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?search=5f4h6w'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?order=FOO'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?order=BAR'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?has_checkin=false'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?has_checkin=true'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    cl = event.checkin_lists.create(name="Default")
    op.checkins.create(datetime=datetime.datetime(2017, 12, 26, 10, 0, 0, tzinfo=UTC), list=cl)
    res['checkins'] = [{'datetime': '2017-12-26T10:00:00Z', 'list': cl.pk}]
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?has_checkin=true'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']

    op.subevent = subevent
    op.save()
    res['subevent'] = subevent.pk

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?subevent={}'.format(organizer.slug, event.slug, subevent.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?subevent__in={},{}'.format(organizer.slug, event.slug,
                                                                                    subevent.pk, subevent2.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?subevent={}'.format(organizer.slug, event.slug,
                                                                             subevent.pk + 1))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_orderposition_detail(token_client, organizer, event, order, item, question):
    res = dict(TEST_ORDERPOSITION_RES)
    op = order.positions.first()
    res["id"] = op.pk
    res["item"] = item.pk
    res["answers"][0]["question"] = question.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(organizer.slug, event.slug,
                                                                                        op.pk))
    assert resp.status_code == 200
    assert res == resp.data

    order.status = 'p'
    order.save()
    event.settings.ticketoutput_pdf__enabled = True
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(organizer.slug, event.slug,
                                                                                        op.pk))
    assert len(resp.data['downloads']) == 1


@pytest.mark.django_db
def test_orderposition_delete(token_client, organizer, event, order, item, question):
    op = order.positions.first()
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
        organizer.slug, event.slug, op.pk
    ))
    assert resp.status_code == 400
    assert resp.data == ['This operation would leave the order empty. Please cancel the order itself instead.']

    op2 = OrderPosition.objects.create(
        order=order,
        item=item,
        variation=None,
        price=Decimal("23"),
        attendee_name_parts={"full_name": "Peter"},
        secret="foobar",
        pseudonymization_id="BAZ",
    )
    order.refresh_from_db()
    order.total = Decimal('46')
    order.save()
    assert order.positions.count() == 2

    resp = token_client.delete('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
        organizer.slug, event.slug, op2.pk
    ))
    assert resp.status_code == 204
    assert order.positions.count() == 1
    order.refresh_from_db()
    assert order.total == Decimal('23.25')


@pytest.fixture
def invoice(order):
    testtime = datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        return generate_invoice(order)


TEST_INVOICE_RES = {
    "order": "FOO",
    "number": "DUMMY-00001",
    "is_cancellation": False,
    "invoice_from": "",
    "invoice_to": "Sample company\n\n\n \nNew Zealand",
    "date": "2017-12-10",
    "refers": None,
    "locale": "en",
    "introductory_text": "",
    "internal_reference": "",
    "additional_text": "",
    "payment_provider_text": "",
    "footer_text": "",
    "foreign_currency_display": None,
    "foreign_currency_rate": None,
    "foreign_currency_rate_date": None,
    "lines": [
        {
            "description": "Budget Ticket<br />Attendee: Peter",
            "gross_value": "23.00",
            "tax_value": "0.00",
            "tax_name": "",
            "tax_rate": "0.00"
        },
        {
            "description": "Payment fee",
            "gross_value": "0.25",
            "tax_value": "0.05",
            "tax_name": "",
            "tax_rate": "19.00"
        }
    ]
}


@pytest.mark.django_db
def test_invoice_list(token_client, organizer, event, order, invoice):
    res = dict(TEST_INVOICE_RES)

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?order=FOO'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?order=BAR'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?number={}'.format(
        organizer.slug, event.slug, invoice.number))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?number=XXX'.format(
        organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?locale=en'.format(
        organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?locale=de'.format(
        organizer.slug, event.slug))
    assert [] == resp.data['results']

    ic = generate_cancellation(invoice)

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?is_cancellation=false'.format(
        organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?is_cancellation=true'.format(
        organizer.slug, event.slug))
    assert len(resp.data['results']) == 1
    assert resp.data['results'][0]['number'] == ic.number

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?refers={}'.format(
        organizer.slug, event.slug, invoice.number))
    assert len(resp.data['results']) == 1
    assert resp.data['results'][0]['number'] == ic.number

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/?refers={}'.format(
        organizer.slug, event.slug, ic.number))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_invoice_detail(token_client, organizer, event, invoice):
    res = dict(TEST_INVOICE_RES)

    resp = token_client.get('/api/v1/organizers/{}/events/{}/invoices/{}/'.format(organizer.slug, event.slug,
                                                                                  invoice.number))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_invoice_regenerate(token_client, organizer, event, invoice):
    InvoiceAddress.objects.filter(order=invoice.order).update(company="ACME Ltd")

    resp = token_client.post('/api/v1/organizers/{}/events/{}/invoices/{}/regenerate/'.format(
        organizer.slug, event.slug, invoice.number
    ))
    assert resp.status_code == 204
    invoice.refresh_from_db()
    assert "ACME Ltd" in invoice.invoice_to


@pytest.mark.django_db
def test_invoice_reissue(token_client, organizer, event, invoice):
    InvoiceAddress.objects.filter(order=invoice.order).update(company="ACME Ltd")

    resp = token_client.post('/api/v1/organizers/{}/events/{}/invoices/{}/reissue/'.format(
        organizer.slug, event.slug, invoice.number
    ))
    assert resp.status_code == 204
    invoice.refresh_from_db()
    assert "ACME Ltd" not in invoice.invoice_to
    assert invoice.order.invoices.count() == 3
    invoice = invoice.order.invoices.last()
    assert "ACME Ltd" in invoice.invoice_to


@pytest.mark.django_db
def test_order_mark_paid_pending(token_client, organizer, event, order):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_paid/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_mark_paid_canceled(token_client, organizer, event, order):
    order.status = Order.STATUS_CANCELED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_paid/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_order_mark_paid_expired_quota_free(token_client, organizer, event, order, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_paid/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_mark_paid_expired_quota_fill(token_client, organizer, event, order, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    quota.size = 0
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_paid/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_mark_paid_locked(token_client, organizer, event, order):
    order.status = Order.STATUS_EXPIRED
    order.save()
    with event.lock():
        resp = token_client.post(
            '/api/v1/organizers/{}/events/{}/orders/{}/mark_paid/'.format(
                organizer.slug, event.slug, order.code
            )
        )
        assert resp.status_code == 409
        order.refresh_from_db()
        assert order.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_mark_canceled_pending(token_client, organizer, event, order):
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_canceled/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_CANCELED
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_order_mark_canceled_pending_no_email(token_client, organizer, event, order):
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_canceled/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'send_email': False
        }
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_CANCELED
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_order_mark_canceled_paid(token_client, organizer, event, order):
    order.status = Order.STATUS_PAID
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_canceled/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_mark_paid_refunded(token_client, organizer, event, order):
    order.status = Order.STATUS_PAID
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_refunded/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_REFUNDED


@pytest.mark.django_db
def test_order_mark_canceled_refunded(token_client, organizer, event, order):
    order.status = Order.STATUS_CANCELED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_refunded/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_order_mark_paid_unpaid(token_client, organizer, event, order):
    order.status = Order.STATUS_PAID
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_pending/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_PENDING


@pytest.mark.django_db
def test_order_mark_canceled_unpaid(token_client, organizer, event, order):
    order.status = Order.STATUS_CANCELED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_pending/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_order_mark_pending_expired(token_client, organizer, event, order):
    order.status = Order.STATUS_PENDING
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_expired/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_mark_paid_expired(token_client, organizer, event, order):
    order.status = Order.STATUS_PAID
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_expired/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_extend_paid(token_client, organizer, event, order):
    order.status = Order.STATUS_PAID
    order.save()
    newdate = (now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/extend/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'expires': newdate
        }
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_extend_pending(token_client, organizer, event, order):
    order.status = Order.STATUS_PENDING
    order.save()
    newdate = (now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/extend/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'expires': newdate
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING
    assert order.expires.strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


@pytest.mark.django_db
def test_order_extend_expired_quota_empty(token_client, organizer, event, order, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    quota.size = 0
    quota.save()
    newdate = (now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/extend/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'expires': newdate
        }
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_extend_expired_quota_ignore(token_client, organizer, event, order, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    quota.size = 0
    quota.save()
    newdate = (now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/extend/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'expires': newdate,
            'force': True
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING
    assert order.expires.strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


@pytest.mark.django_db
def test_order_extend_expired_quota_waiting_list(token_client, organizer, event, order, item, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    quota.size = 1
    quota.save()
    event.waitinglistentries.create(item=item, email='foo@bar.com')
    newdate = (now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/extend/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'expires': newdate,
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING
    assert order.expires.strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


@pytest.mark.django_db
def test_order_extend_expired_quota_left(token_client, organizer, event, order, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    quota.size = 2
    quota.save()
    newdate = (now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/extend/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'expires': newdate,
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING
    assert order.expires.strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


@pytest.mark.django_db
def test_order_pending_approve(token_client, organizer, event, order):
    order.require_approval = True
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/approve/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_PENDING
    assert not resp.data['require_approval']


@pytest.mark.django_db
def test_order_invalid_state_approve(token_client, organizer, event, order):
    order.require_approval = True
    order.status = Order.STATUS_CANCELED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/approve/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400

    order.require_approval = False
    order.status = Order.STATUS_PENDING
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/approve/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_order_pending_deny(token_client, organizer, event, order):
    order.require_approval = True
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/deny/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_CANCELED
    assert resp.data['require_approval']


@pytest.mark.django_db
def test_order_invalid_state_deny(token_client, organizer, event, order):
    order.require_approval = True
    order.status = Order.STATUS_CANCELED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/deny/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400

    order.require_approval = False
    order.status = Order.STATUS_PENDING
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/deny/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400


ORDER_CREATE_PAYLOAD = {
    "email": "dummy@dummy.test",
    "locale": "en",
    "fees": [
        {
            "fee_type": "payment",
            "value": "0.25",
            "description": "",
            "internal_type": "",
            "tax_rule": None
        }
    ],
    "payment_provider": "banktransfer",
    "invoice_address": {
        "is_business": False,
        "company": "Sample company",
        "name": "Fo",
        "street": "Bar",
        "zipcode": "",
        "city": "Sample City",
        "country": "NZ",
        "internal_reference": "",
        "vat_id": ""
    },
    "positions": [
        {
            "positionid": 1,
            "item": 1,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [
                {
                    "question": 1,
                    "answer": "S",
                    "options": []
                }
            ],
            "subevent": None
        }
    ],
}


@pytest.mark.django_db
def test_order_create(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    assert o.email == "dummy@dummy.test"
    assert o.locale == "en"
    assert o.total == Decimal('23.25')
    assert o.status == Order.STATUS_PENDING

    p = o.payments.first()
    assert p.provider == "banktransfer"
    assert p.amount == o.total
    assert p.state == "created"

    fee = o.fees.first()
    assert fee.fee_type == "payment"
    assert fee.value == Decimal('0.25')
    ia = o.invoice_address
    assert ia.company == "Sample company"
    assert o.positions.count() == 1
    pos = o.positions.first()
    assert pos.item == item
    assert pos.price == Decimal("23.00")
    answ = pos.answers.first()
    assert answ.question == question
    assert answ.answer == "S"


@pytest.mark.django_db
def test_order_create_invoice_address_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['invoice_address']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    with pytest.raises(InvoiceAddress.DoesNotExist):
        o.invoice_address


@pytest.mark.django_db
def test_order_create_legacy_attendee_name(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['attendee_name'] = 'Peter'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    del res['positions'][0]['attendee_name_parts']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    assert o.positions.first().attendee_name_parts == {"_legacy": "Peter"}


@pytest.mark.django_db
def test_order_create_code_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['code'] = 'ABCDE'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    assert o.code == "ABCDE"

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'code': ['This order code is already in use.']}

    res['code'] = 'ABaDE'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'code': ['This order code contains invalid characters.']}


@pytest.mark.django_db
def test_order_email_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['email']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    assert not o.email


@pytest.mark.django_db
def test_order_create_payment_info_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])

    res['payment_info'] = {
        'foo': {
            'bar': [1, 2],
            'test': False
        }
    }
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])

    p = o.payments.first()
    assert p.provider == "banktransfer"
    assert p.amount == o.total
    assert json.loads(p.info) == res['payment_info']


@pytest.mark.django_db
def test_order_create_position_secret_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    assert o.positions.first().secret

    res['positions'][0]['secret'] = "aaa"
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    assert o.positions.first().secret == "aaa"

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400

    assert resp.data == {'positions': [{'secret': ['You cannot assign a position secret that already exists.']}]}


@pytest.mark.django_db
def test_order_create_tax_rules(token_client, organizer, event, item, quota, question, taxrule):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'][0]['tax_rule'] = taxrule.pk
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    item.tax_rule = taxrule
    item.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    fee = o.fees.first()
    assert fee.fee_type == "payment"
    assert fee.value == Decimal('0.25')
    assert fee.tax_rate == Decimal('19.00')
    assert fee.tax_rule == taxrule
    ia = o.invoice_address
    assert ia.company == "Sample company"
    pos = o.positions.first()
    assert pos.item == item
    assert pos.tax_rate == Decimal('19.00')
    assert pos.tax_value == Decimal('3.67')
    assert pos.tax_rule == taxrule


@pytest.mark.django_db
def test_order_create_fee_type_validation(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'][0]['fee_type'] = 'unknown'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'fees': [{'fee_type': ['"unknown" is not a valid choice.']}]}


@pytest.mark.django_db
def test_order_create_tax_rule_wrong_event(token_client, organizer, event, item, quota, question, taxrule2):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'][0]['tax_rule'] = taxrule2.pk
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'fees': [{'tax_rule': ['The specified tax rate does not belong to this event.']}]}


@pytest.mark.django_db
def test_order_create_subevent_not_allowed(token_client, organizer, event, item, quota, question, subevent2):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['subevent'] = subevent2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'subevent': ['You cannot set a subevent for this event.']}]}


@pytest.mark.django_db
def test_order_create_empty(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'] = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': ['An order cannot be empty.']}


@pytest.mark.django_db
def test_order_create_subevent_validation(token_client, organizer, event, item, subevent, subevent2, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'subevent': ['You need to set a subevent.']}]}

    res['positions'][0]['subevent'] = subevent2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'subevent': ['The specified subevent does not belong to this event.']}]}


@pytest.mark.django_db
def test_order_create_item_validation(token_client, organizer, event, item, item2, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    item.active = False
    item.save()
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'item': ['The specified item is not active.']}]}
    item.active = True
    item.save()

    res['positions'][0]['item'] = item2.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'item': ['The specified item does not belong to this event.']}]}

    var2 = item2.variations.create(value="A")
    quota.variations.add(var2)

    res['positions'][0]['item'] = item.pk
    res['positions'][0]['variation'] = var2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'variation': ['You cannot specify a variation for this item.']}]}

    var1 = item.variations.create(value="A")
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['variation'] = var1.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'item': ['The product "Budget Ticket" is not assigned to a quota.']}]}

    quota.variations.add(var1)
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201

    res['positions'][0]['variation'] = var2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [{'variation': ['The specified variation does not belong to the specified item.']}]}

    res['positions'][0]['variation'] = None
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'variation': ['You should specify a variation for this item.']}]}


@pytest.mark.django_db
def test_order_create_positionids_addons(token_client, organizer, event, item, quota):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None
        },
        {
            "positionid": 2,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": 1,
            "answers": [],
            "subevent": None
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    pos1 = o.positions.first()
    pos2 = o.positions.last()
    assert pos2.addon_to == pos1


@pytest.mark.django_db
def test_order_create_positionid_validation(token_client, organizer, event, item, quota):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None
        },
        {
            "positionid": 2,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": 2,
            "answers": [],
            "subevent": None
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {},
            {
                'addon_to': [
                    'If you set addon_to, you need to make sure that the '
                    'referenced position ID exists and is transmitted directly '
                    'before its add-ons.'
                ]
            }
        ]
    }

    res['positions'] = [
        {
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None
        },
        {
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": 2,
            "answers": [],
            "subevent": None
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [
        {'positionid': ["If you set addon_to on any position, you need to specify position IDs manually."]},
        {'positionid': ["If you set addon_to on any position, you need to specify position IDs manually."]}
    ]}

    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "answers": [],
            "subevent": None
        },
        {
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "answers": [],
            "subevent": None
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {},
            {
                'positionid': ['If you set position IDs manually, you need to do so for all positions.']
            }
        ]
    }

    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "answers": [],
            "subevent": None
        },
        {
            "positionid": 3,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "answers": [],
            "subevent": None
        }
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {},
            {
                'positionid': ['Position IDs need to be consecutive.']
            }
        ]
    }


@pytest.mark.django_db
def test_order_create_answer_validation(token_client, organizer, event, item, quota, question, question2):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [{'answers': [{'question': ['The specified question does not belong to this event.']}]}]}

    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['answers'][0]['options'] = [question.options.first().pk]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'answers': [
        {'non_field_errors': ['You should not specify options if the question is not of a choice type.']}]}]}

    question.type = Question.TYPE_CHOICE
    question.save()
    res['positions'][0]['answers'][0]['options'] = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [
        {'answers': [{'non_field_errors': ['You need to specify options if the question is of a choice type.']}]}]}

    question.options.create(answer="L")
    res['positions'][0]['answers'][0]['options'] = [
        question.options.first().pk,
        question.options.last().pk,
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [{'answers': [{'non_field_errors': ['You can specify at most one option for this question.']}]}]}

    question.type = Question.TYPE_FILE
    question.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [{'answers': [{'non_field_errors': ['File uploads are currently not supported via the API.']}]}]}

    question.type = Question.TYPE_CHOICE_MULTIPLE
    question.save()
    res['positions'][0]['answers'][0]['options'] = [
        question.options.first().pk,
        question.options.last().pk,
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    pos = o.positions.first()
    answ = pos.answers.first()
    assert answ.question == question
    assert answ.answer == "XL, L"

    question.type = Question.TYPE_NUMBER
    question.save()
    res['positions'][0]['answers'][0]['options'] = []
    res['positions'][0]['answers'][0]['answer'] = '3.45'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    pos = o.positions.first()
    answ = pos.answers.first()
    assert answ.answer == "3.45"

    question.type = Question.TYPE_NUMBER
    question.save()
    res['positions'][0]['answers'][0]['options'] = []
    res['positions'][0]['answers'][0]['answer'] = 'foo'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'answers': [{'non_field_errors': ['A valid number is required.']}]}]}

    question.type = Question.TYPE_BOOLEAN
    question.save()
    res['positions'][0]['answers'][0]['options'] = []
    res['positions'][0]['answers'][0]['answer'] = 'True'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    pos = o.positions.first()
    answ = pos.answers.first()
    assert answ.answer == "True"

    question.type = Question.TYPE_BOOLEAN
    question.save()
    res['positions'][0]['answers'][0]['answer'] = '0'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    pos = o.positions.first()
    answ = pos.answers.first()
    assert answ.answer == "False"

    question.type = Question.TYPE_BOOLEAN
    question.save()
    res['positions'][0]['answers'][0]['answer'] = 'bla'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [{'answers': [{'non_field_errors': ['Please specify "true" or "false" for boolean questions.']}]}]}

    question.type = Question.TYPE_DATE
    question.save()
    res['positions'][0]['answers'][0]['answer'] = '2018-05-14'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    pos = o.positions.first()
    answ = pos.answers.first()
    assert answ.answer == "2018-05-14"

    question.type = Question.TYPE_DATE
    question.save()
    res['positions'][0]['answers'][0]['answer'] = 'bla'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'answers': [
        {'non_field_errors': ['Date has wrong format. Use one of these formats instead: YYYY[-MM[-DD]].']}]}]}

    question.type = Question.TYPE_DATETIME
    question.save()
    res['positions'][0]['answers'][0]['answer'] = '2018-05-14T13:00:00Z'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    pos = o.positions.first()
    answ = pos.answers.first()
    assert answ.answer == "2018-05-14 13:00:00+00:00"

    question.type = Question.TYPE_DATETIME
    question.save()
    res['positions'][0]['answers'][0]['answer'] = 'bla'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'answers': [{'non_field_errors': [
        'Datetime has wrong format. Use one of these formats instead: '
        'YYYY-MM-DDThh:mm[:ss[.uuuuuu]][+HH:MM|-HH:MM|Z].']}]}]}

    question.type = Question.TYPE_TIME
    question.save()
    res['positions'][0]['answers'][0]['answer'] = '13:00:00'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    pos = o.positions.first()
    answ = pos.answers.first()
    assert answ.answer == "13:00:00"

    question.type = Question.TYPE_TIME
    question.save()
    res['positions'][0]['answers'][0]['answer'] = 'bla'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'answers': [
        {'non_field_errors': ['Time has wrong format. Use one of these formats instead: hh:mm[:ss[.uuuuuu]].']}]}]}


@pytest.mark.django_db
def test_order_create_quota_validation(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'] = [
        {
            "positionid": 1,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": None,
            "answers": [],
            "subevent": None
        },
        {
            "positionid": 2,
            "item": item.pk,
            "variation": None,
            "price": "23.00",
            "attendee_name_parts": {"full_name": "Peter"},
            "attendee_email": None,
            "addon_to": 1,
            "answers": [],
            "subevent": None
        }
    ]

    quota.size = 0
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'item': ['There is not enough quota available on quota "Budget Quota" to perform the operation.']},
            {'item': ['There is not enough quota available on quota "Budget Quota" to perform the operation.']},
        ]
    }

    quota.size = 1
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {},
            {'item': ['There is not enough quota available on quota "Budget Quota" to perform the operation.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_quota_consume_cart(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk

    cr = CartPosition.objects.create(
        event=event, cart_id="uxLJBUMEcnxOLI2EuxLYN1hWJq9GKu4yWL9FEgs2m7M0vdFi@api", item=item,
        price=23,
        expires=now() + datetime.timedelta(hours=3)
    )

    quota.size = 1
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'item': ['There is not enough quota available on quota "Budget Quota" to perform the operation.']},
        ]
    }

    res['consume_carts'] = [cr.cart_id]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert not CartPosition.objects.filter(pk=cr.pk).exists()


@pytest.mark.django_db
def test_order_create_free(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'] = []
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['price'] = '0.00'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    assert o.total == Decimal('0.00')
    assert o.status == Order.STATUS_PAID

    p = o.payments.first()
    assert p.provider == "free"
    assert p.amount == o.total
    assert p.state == "confirmed"


@pytest.mark.django_db
def test_order_create_require_payment_provider(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    del res['payment_provider']
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'payment_provider': ['This field is required.']}


@pytest.mark.django_db
def test_order_create_invalid_payment_provider(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['payment_provider'] = 'foo'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'payment_provider': ['The given payment provider is not known.']}


@pytest.mark.django_db
def test_order_create_invalid_free_order(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['payment_provider'] = 'free'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == ['You cannot use the "free" payment provider for non-free orders.']


@pytest.mark.django_db
def test_order_create_invalid_status(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['status'] = 'e'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'status': ['"e" is not a valid choice.']}


@pytest.mark.django_db
def test_order_create_paid_generate_invoice(token_client, organizer, event, item, quota, question):
    event.settings.invoice_generate = 'paid'
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['status'] = 'p'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    o = Order.objects.get(code=resp.data['code'])
    assert o.invoices.count() == 1

    p = o.payments.first()
    assert p.provider == "banktransfer"
    assert p.amount == o.total
    assert p.state == "confirmed"


REFUND_CREATE_PAYLOAD = {
    "state": "created",
    "provider": "manual",
    "amount": "23.00",
    "source": "admin",
    "payment": 2,
    "info": {
        "foo": "bar",
    }
}


@pytest.mark.django_db
def test_refund_create(token_client, organizer, event, order):
    res = copy.deepcopy(REFUND_CREATE_PAYLOAD)
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data=res
    )
    assert resp.status_code == 201
    r = order.refunds.get(local_id=resp.data['local_id'])
    assert r.provider == "manual"
    assert r.amount == Decimal("23.00")
    assert r.state == "created"
    assert r.source == "admin"
    assert r.info_data == {"foo": "bar"}
    assert r.payment.local_id == 2
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_refund_create_mark_refunded(token_client, organizer, event, order):
    res = copy.deepcopy(REFUND_CREATE_PAYLOAD)
    res['mark_refunded'] = True
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data=res
    )
    assert resp.status_code == 201
    r = order.refunds.get(local_id=resp.data['local_id'])
    assert r.provider == "manual"
    assert r.amount == Decimal("23.00")
    assert r.state == "created"
    assert r.source == "admin"
    assert r.info_data == {"foo": "bar"}
    assert r.payment.local_id == 2
    order.refresh_from_db()
    assert order.status == Order.STATUS_REFUNDED


@pytest.mark.django_db
def test_refund_optional_fields(token_client, organizer, event, order):
    res = copy.deepcopy(REFUND_CREATE_PAYLOAD)
    del res['info']
    del res['payment']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data=res
    )
    assert resp.status_code == 201
    r = order.refunds.get(local_id=resp.data['local_id'])
    assert r.provider == "manual"
    assert r.amount == Decimal("23.00")
    assert r.state == "created"
    assert r.source == "admin"

    del res['state']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data=res
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_refund_create_invalid_payment(token_client, organizer, event, order):
    res = copy.deepcopy(REFUND_CREATE_PAYLOAD)
    res['payment'] = 7
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data=res
    )
    assert resp.status_code == 400
