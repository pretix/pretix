import copy
import datetime
import json
from decimal import Decimal
from unittest import mock

import pytest
from django.core import mail as djmail
from django.dispatch import receiver
from django.utils.timezone import now
from django_countries.fields import Country
from django_scopes import scopes_disabled
from pytz import UTC
from stripe.error import APIConnectionError
from tests.plugins.stripe.test_provider import MockedCharge

from pretix.base.channels import SalesChannel
from pretix.base.models import (
    InvoiceAddress, Order, OrderPosition, Question, SeatingPlan,
)
from pretix.base.models.orders import (
    CartPosition, OrderFee, OrderPayment, OrderRefund, QuestionAnswer,
)
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice,
)
from pretix.base.signals import register_sales_channels


class FoobarSalesChannel(SalesChannel):
    identifier = "bar"
    verbose_name = "Foobar"
    icon = "home"
    testmode_supported = False


@receiver(register_sales_channels, dispatch_uid="test_orders_register_sales_channels")
def base_sales_channels(sender, **kwargs):
    return (
        FoobarSalesChannel(),
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
        o.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.25'), tax_rate=Decimal('19.00'),
                      tax_value=Decimal('0.05'), tax_rule=taxrule, canceled=True)
        InvoiceAddress.objects.create(order=o, company="Sample company", country=Country('NZ'),
                                      vat_id="DE123", vat_id_validated=True)
        op = OrderPosition.objects.create(
            order=o,
            item=item,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={"full_name": "Peter", "_scheme": "full"},
            secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
            pseudonymization_id="ABCDEFGHKL",
        )
        OrderPosition.objects.create(
            order=o,
            item=item,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={"full_name": "Peter", "_scheme": "full"},
            secret="YBiYJrmF5ufiTLdV1iDf",
            pseudonymization_id="JKLM",
            canceled=True
        )
        op.answers.create(question=question, answer='S')
        return o


@pytest.fixture
def clist_autocheckin(event):
    c = event.checkin_lists.create(name="Default", all_products=True, auto_checkin_sales_channels=['web'])
    return c


TEST_ORDERPOSITION_RES = {
    "id": 1,
    "order": "FOO",
    "positionid": 1,
    "item": 1,
    "variation": None,
    "price": "23.00",
    "attendee_name_parts": {"full_name": "Peter", "_scheme": "full"},
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
    "seat": None,
    "company": None,
    "street": None,
    "zipcode": None,
    "city": None,
    "country": None,
    "state": None,
    "answers": [
        {
            "question": 1,
            "answer": "S",
            "question_identifier": "ABC",
            "options": [],
            "option_identifiers": []
        }
    ],
    "subevent": None,
    "canceled": False,
}
TEST_PAYMENTS_RES = [
    {
        "local_id": 1,
        "created": "2017-12-01T10:00:00Z",
        "payment_date": "2017-12-01T10:00:00Z",
        "provider": "stripe",
        "payment_url": None,
        "details": {
            "id": None,
            "payment_method": None
        },
        "state": "refunded",
        "amount": "23.00"
    },
    {
        "local_id": 2,
        "created": "2017-12-01T10:00:00Z",
        "payment_date": None,
        "provider": "banktransfer",
        "payment_url": None,
        "details": {},
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
    "testmode": False,
    "secret": "k24fiuwvu8kxz3y1",
    "email": "dummy@dummy.test",
    "locale": "en",
    "datetime": "2017-12-01T10:00:00Z",
    "expires": "2017-12-10T10:00:00Z",
    "payment_date": "2017-12-01",
    "sales_channel": "web",
    "fees": [
        {
            "canceled": False,
            "fee_type": "payment",
            "value": "0.25",
            "description": "",
            "internal_type": "",
            "tax_rate": "19.00",
            "tax_value": "0.05"
        }
    ],
    "url": "http://example.com/dummy/dummy/order/FOO/k24fiuwvu8kxz3y1/",
    "payment_provider": "banktransfer",
    "total": "23.00",
    "comment": "",
    "checkin_attention": False,
    "invoice_address": {
        "last_modified": "2017-12-01T10:00:00Z",
        "is_business": False,
        "company": "Sample company",
        "name": "",
        "name_parts": {},
        "street": "",
        "zipcode": "",
        "city": "",
        "country": "NZ",
        "state": "",
        "internal_reference": "",
        "vat_id": "DE123",
        "vat_id_validated": True
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
    with scopes_disabled():
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

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?testmode=false'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?testmode=true'.format(organizer.slug, event.slug))
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

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?include_canceled_positions=false'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert len(resp.data['results'][0]['positions']) == 1

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?include_canceled_positions=true'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert len(resp.data['results'][0]['positions']) == 2

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?include_canceled_fees=false'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert len(resp.data['results'][0]['fees']) == 1

    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/?include_canceled_fees=true'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert len(resp.data['results'][0]['fees']) == 2


@pytest.mark.django_db
def test_order_detail(token_client, organizer, event, order, item, taxrule, question):
    res = dict(TEST_ORDER_RES)
    with scopes_disabled():
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

    assert len(resp.data['positions']) == 1
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/?include_canceled_positions=true'.format(organizer.slug, event.slug, order.code))
    assert resp.status_code == 200
    assert len(resp.data['positions']) == 2

    assert len(resp.data['fees']) == 1
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orders/{}/?include_canceled_fees=true'.format(organizer.slug, event.slug, order.code))
    assert resp.status_code == 200
    assert len(resp.data['fees']) == 2


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
def test_payment_create_confirmed(token_client, organizer, event, order):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'provider': 'banktransfer',
        'state': 'confirmed',
        'amount': order.total,
        'info': {
            'foo': 'bar'
        }
    })
    with scopes_disabled():
        p = order.payments.last()
    assert resp.status_code == 201
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    assert p.info_data == {'foo': 'bar'}
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_payment_create_pending(token_client, organizer, event, order):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'provider': 'banktransfer',
        'state': 'pending',
        'amount': order.total,
        'info': {
            'foo': 'bar'
        }
    })
    with scopes_disabled():
        p = order.payments.last()
    assert resp.status_code == 201
    assert p.state == OrderPayment.PAYMENT_STATE_PENDING
    assert p.info_data == {'foo': 'bar'}
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_payment_confirm(token_client, organizer, event, order):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/confirm/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'force': True})
    with scopes_disabled():
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
    with scopes_disabled():
        p = order.payments.get(local_id=2)
    assert resp.status_code == 200
    assert p.state == OrderPayment.PAYMENT_STATE_CANCELED

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/cancel/'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 400


@pytest.mark.django_db
def test_payment_refund_fail(token_client, organizer, event, order, monkeypatch):
    with scopes_disabled():
        order.payments.last().confirm()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'amount': '25.00',
        'mark_canceled': False
    })
    assert resp.status_code == 400
    assert resp.data == {'amount': ['Invalid refund amount, only 23.00 are available to refund.']}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'amount': '20.00',
        'mark_canceled': False
    })
    assert resp.status_code == 400
    assert resp.data == {'amount': ['Partial refund not available for this payment method.']}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'mark_canceled': False
    })
    assert resp.status_code == 400
    assert resp.data == {'amount': ['Full refund not available for this payment method.']}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/2/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'amount': '23.00',
        'mark_canceled': False
    })
    assert resp.status_code == 400
    assert resp.data == {'amount': ['Full refund not available for this payment method.']}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/payments/1/refund/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={
        'amount': '23.00',
        'mark_canceled': False
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

    with scopes_disabled():
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
        'mark_canceled': False,
    })
    assert resp.status_code == 200
    with scopes_disabled():
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

    with scopes_disabled():
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
        'mark_canceled': False,
    })
    assert resp.status_code == 400
    assert resp.data == {'detail': 'External error: We had trouble communicating with Stripe. Please try again and contact support if the problem persists.'}
    with scopes_disabled():
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
    with scopes_disabled():
        r = order.refunds.get(local_id=1)
    r.state = 'transit'
    r.save()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/done/'.format(
        organizer.slug, event.slug, order.code
    ))
    with scopes_disabled():
        r = order.refunds.get(local_id=1)
    assert resp.status_code == 200
    assert r.state == OrderRefund.REFUND_STATE_DONE

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/done/'.format(
        organizer.slug, event.slug, order.code
    ))
    assert resp.status_code == 400


@pytest.mark.django_db
def test_refund_process_mark_refunded(token_client, organizer, event, order):
    with scopes_disabled():
        p = order.payments.get(local_id=1)
        p.create_external_refund()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/2/process/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'mark_canceled': True})
    with scopes_disabled():
        r = order.refunds.get(local_id=1)
    assert resp.status_code == 200
    assert r.state == OrderRefund.REFUND_STATE_DONE
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELED

    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/2/process/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'mark_canceled': True})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_refund_process_mark_pending(token_client, organizer, event, order):
    with scopes_disabled():
        p = order.payments.get(local_id=1)
        p.create_external_refund()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/2/process/'.format(
        organizer.slug, event.slug, order.code
    ), format='json', data={'mark_canceled': False})
    with scopes_disabled():
        r = order.refunds.get(local_id=1)
    assert resp.status_code == 200
    assert r.state == OrderRefund.REFUND_STATE_DONE
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_refund_cancel(token_client, organizer, event, order):
    with scopes_disabled():
        r = order.refunds.get(local_id=1)
    r.state = 'transit'
    r.save()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/orders/{}/refunds/1/cancel/'.format(
        organizer.slug, event.slug, order.code
    ))
    with scopes_disabled():
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
    with scopes_disabled():
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

    with scopes_disabled():
        cl = event.checkin_lists.create(name="Default")
        op.checkins.create(datetime=datetime.datetime(2017, 12, 26, 10, 0, 0, tzinfo=UTC), list=cl)
    res['checkins'] = [{'datetime': '2017-12-26T10:00:00Z', 'list': cl.pk, 'auto_checked_in': False}]
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

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?include_canceled_positions=false'.format(organizer.slug, event.slug))
    assert len(resp.data['results']) == 1
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?include_canceled_positions=true'.format(organizer.slug, event.slug))
    assert len(resp.data['results']) == 2


@pytest.mark.django_db
def test_orderposition_detail(token_client, organizer, event, order, item, question):
    res = dict(TEST_ORDERPOSITION_RES)
    with scopes_disabled():
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
def test_orderposition_detail_canceled(token_client, organizer, event, order, item, question):
    with scopes_disabled():
        op = order.all_positions.filter(canceled=True).first()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(organizer.slug, event.slug,
                                                                                        op.pk))
    assert resp.status_code == 404
    resp = token_client.get('/api/v1/organizers/{}/events/{}/orderpositions/{}/?include_canceled_positions=true'.format(
        organizer.slug, event.slug, op.pk))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_orderposition_delete(token_client, organizer, event, order, item, question):
    with scopes_disabled():
        op = order.positions.first()
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/orderpositions/{}/'.format(
        organizer.slug, event.slug, op.pk
    ))
    assert resp.status_code == 400
    assert resp.data == ['This operation would leave the order empty. Please cancel the order itself instead.']

    with scopes_disabled():
        op2 = OrderPosition.objects.create(
            order=order,
            item=item,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={"full_name": "Peter", "_scheme": "full"},
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
    with scopes_disabled():
        assert order.positions.count() == 1
        assert order.all_positions.count() == 3
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
    "invoice_to": "Sample company\nNew Zealand\nVAT-ID: DE123",
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
            "position": 1,
            "description": "Budget Ticket<br />Attendee: Peter",
            "gross_value": "23.00",
            "tax_value": "0.00",
            "tax_name": "",
            "tax_rate": "0.00"
        },
        {
            "position": 2,
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

    with scopes_disabled():
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
    with scopes_disabled():
        InvoiceAddress.objects.filter(order=invoice.order).update(company="ACME Ltd")

    resp = token_client.post('/api/v1/organizers/{}/events/{}/invoices/{}/regenerate/'.format(
        organizer.slug, event.slug, invoice.number
    ))
    assert resp.status_code == 204
    invoice.refresh_from_db()
    assert "ACME Ltd" in invoice.invoice_to


@pytest.mark.django_db
def test_invoice_reissue(token_client, organizer, event, invoice):
    with scopes_disabled():
        InvoiceAddress.objects.filter(order=invoice.order).update(company="ACME Ltd")

    resp = token_client.post('/api/v1/organizers/{}/events/{}/invoices/{}/reissue/'.format(
        organizer.slug, event.slug, invoice.number
    ))
    assert resp.status_code == 204
    invoice.refresh_from_db()
    assert "ACME Ltd" not in invoice.invoice_to
    with scopes_disabled():
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
def test_order_reactivate(token_client, organizer, event, order, quota):
    order.status = Order.STATUS_CANCELED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/reactivate/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_PENDING


@pytest.mark.django_db
def test_order_reactivate_invalid(token_client, organizer, event, order):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/reactivate/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 400


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
def test_order_mark_canceled_pending_fee_not_allowed(token_client, organizer, event, order):
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_canceled/'.format(
            organizer.slug, event.slug, order.code
        ), data={
            'cancellation_fee': '7.00'
        }
    )
    assert resp.status_code == 400
    assert resp.data == {'detail': 'The cancellation fee cannot be higher than the payment credit of this order.'}


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
def test_order_mark_canceled_expired(token_client, organizer, event, order):
    order.status = Order.STATUS_EXPIRED
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_canceled/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_order_mark_paid_canceled_keep_fee(token_client, organizer, event, order):
    order.status = Order.STATUS_PAID
    order.save()
    with scopes_disabled():
        order.payments.create(state=OrderPayment.PAYMENT_STATE_CONFIRMED, amount=order.total)
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_canceled/'.format(
            organizer.slug, event.slug, order.code
        ), data={
            'cancellation_fee': '6.00'
        }
    )
    assert resp.status_code == 200
    assert resp.data['status'] == Order.STATUS_PAID
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID
    assert order.total == Decimal('6.00')


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
    assert resp.data['status'] == Order.STATUS_CANCELED


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
    assert order.expires.astimezone(event.timezone).strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


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
    assert order.expires.astimezone(event.timezone).strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


@pytest.mark.django_db
def test_order_extend_expired_quota_waiting_list(token_client, organizer, event, order, item, quota):
    order.status = Order.STATUS_EXPIRED
    order.save()
    quota.size = 1
    quota.save()
    with scopes_disabled():
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
    assert order.expires.astimezone(event.timezone).strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


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
    assert order.expires.astimezone(event.timezone).strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


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
    "sales_channel": "web",
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
        "name_parts": {"full_name": "Fo"},
        "street": "Bar",
        "state": "",
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
            "company": "FOOCORP",
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
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
    assert o.email == "dummy@dummy.test"
    assert o.locale == "en"
    assert o.total == Decimal('23.25')
    assert o.status == Order.STATUS_PENDING
    assert o.sales_channel == "web"
    assert not o.testmode

    with scopes_disabled():
        p = o.payments.first()
    assert p.provider == "banktransfer"
    assert p.amount == o.total
    assert p.state == "created"

    with scopes_disabled():
        fee = o.fees.first()
    assert fee.fee_type == "payment"
    assert fee.value == Decimal('0.25')
    ia = o.invoice_address
    assert ia.company == "Sample company"
    assert ia.name_parts == {"full_name": "Fo", "_scheme": "full"}
    assert ia.name_cached == "Fo"
    with scopes_disabled():
        assert o.positions.count() == 1
        pos = o.positions.first()
    assert pos.item == item
    assert pos.price == Decimal("23.00")
    assert pos.attendee_name_parts == {"full_name": "Peter", "_scheme": "full"}
    assert pos.company == "FOOCORP"
    with scopes_disabled():
        answ = pos.answers.first()
    assert answ.question == question
    assert answ.answer == "S"


@pytest.mark.django_db
def test_order_create_simulate(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    question.type = Question.TYPE_CHOICE_MULTIPLE
    question.save()
    with scopes_disabled():
        opt = question.options.create(answer="L")
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['answers'][0]['options'] = [opt.pk]
    res['simulate'] = True
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        assert Order.objects.count() == 0
        assert QuestionAnswer.objects.count() == 0
        assert OrderPosition.objects.count() == 0
        assert OrderFee.objects.count() == 0
        assert InvoiceAddress.objects.count() == 0
    d = resp.data
    del d['last_modified']
    del d['secret']
    del d['url']
    del d['expires']
    del d['invoice_address']['last_modified']
    del d['positions'][0]['secret']
    assert d == {
        'code': 'PREVIEW',
        'status': 'n',
        'testmode': False,
        'email': 'dummy@dummy.test',
        'locale': 'en',
        'datetime': None,
        'payment_date': None,
        'payment_provider': None,
        'fees': [
            {
                'fee_type': 'payment',
                'value': '0.25',
                'description': '',
                'internal_type': '',
                'tax_rate': '0.00',
                'tax_value': '0.00',
                'tax_rule': None,
                'canceled': False
            }
        ],
        'total': '23.25',
        'comment': '',
        'invoice_address': {
            'is_business': False,
            'company': 'Sample company',
            'name': 'Fo',
            'name_parts': {'full_name': 'Fo', '_scheme': 'full'},
            'street': 'Bar',
            'zipcode': '',
            'city': 'Sample City',
            'country': 'NZ',
            'state': '',
            'vat_id': '',
            'vat_id_validated': False,
            'internal_reference': ''
        },
        'positions': [
            {
                'id': 0,
                'order': '',
                'positionid': 1,
                'item': item.pk,
                'variation': None,
                'price': '23.00',
                'attendee_name': 'Peter',
                'attendee_name_parts': {'full_name': 'Peter', '_scheme': 'full'},
                'attendee_email': None,
                'voucher': None,
                'tax_rate': '0.00',
                'tax_value': '0.00',
                'addon_to': None,
                'subevent': None,
                'checkins': [],
                'downloads': [],
                'answers': [
                    {'question': question.pk, 'answer': 'L', 'question_identifier': 'ABC',
                     'options': [opt.pk],
                     'option_identifiers': [opt.identifier]}
                ],
                'tax_rule': None,
                'pseudonymization_id': 'PREVIEW',
                'seat': None,
                'company': "FOOCORP",
                'street': None,
                'city': None,
                'zipcode': None,
                'state': None,
                'country': None,
                'canceled': False
            }
        ],
        'downloads': [],
        'checkin_attention': False,
        'payments': [],
        'refunds': [],
        'require_approval': False,
        'sales_channel': 'web',
    }


@pytest.mark.django_db
def test_order_create_autocheckin(token_client, organizer, event, item, quota, question, clist_autocheckin):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert "web" in clist_autocheckin.auto_checkin_sales_channels
        assert o.positions.first().checkins.first().auto_checked_in

    clist_autocheckin.auto_checkin_sales_channels = []
    clist_autocheckin.save()

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert clist_autocheckin.auto_checkin_sales_channels == []
        assert o.positions.first().checkins.count() == 0


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
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        with pytest.raises(InvoiceAddress.DoesNotExist):
            o.invoice_address


@pytest.mark.django_db
def test_order_create_sales_channel_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['sales_channel']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
    assert o.sales_channel == "web"


@pytest.mark.django_db
def test_order_create_sales_channel_invalid(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['sales_channel'] = 'foo'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'sales_channel': ['Unknown sales channel.']}


@pytest.mark.django_db
def test_order_create_in_test_mode(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['testmode'] = True
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
    assert o.testmode


@pytest.mark.django_db
def test_order_create_in_test_mode_saleschannel_limited(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['testmode'] = True
    res['sales_channel'] = 'bar'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'testmode': ['This sales channel does not provide support for testmode.']}


@pytest.mark.django_db
def test_order_create_attendee_name_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['attendee_name'] = None
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['attendee_name_parts']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.positions.first().attendee_name_parts == {}


@pytest.mark.django_db
def test_order_create_legacy_attendee_name(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['attendee_name'] = 'Peter'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk

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

    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.positions.first().attendee_name_parts == {"_legacy": "Peter"}


@pytest.mark.django_db
def test_order_create_legacy_invoice_name(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['invoice_address']['name'] = 'Peter'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    del res['invoice_address']['name_parts']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.invoice_address.name_parts == {"_legacy": "Peter"}


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
    with scopes_disabled():
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
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
    assert not o.email


@pytest.mark.django_db
def test_order_create_payment_provider_optional_free(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['price'] = '0.00'
    res['positions'][0]['status'] = 'p'
    del res['payment_provider']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert not o.payments.exists()


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
    with scopes_disabled():
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
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.positions.first().secret

    res['positions'][0]['secret'] = "aaa"
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
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
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        fee = o.fees.first()
    assert fee.fee_type == "payment"
    assert fee.value == Decimal('0.25')
    assert fee.tax_rate == Decimal('19.00')
    assert fee.tax_rule == taxrule
    ia = o.invoice_address
    assert ia.company == "Sample company"
    with scopes_disabled():
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
def test_order_create_fee_as_percentage(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'][0]['_treat_value_as_percentage'] = True
    res['fees'][0]['value'] = '10.00'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        fee = o.fees.first()
        assert fee.value == Decimal('2.30')
        assert o.total == Decimal('25.30')


@pytest.mark.django_db
def test_order_create_fee_with_auto_tax(token_client, organizer, event, item, quota, question, taxrule):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['fees'][0]['_split_taxes_like_products'] = True
    res['fees'][0]['_treat_value_as_percentage'] = True
    res['fees'][0]['value'] = '10.00'
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
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        fee = o.fees.first()
        assert fee.value == Decimal('2.30')
        assert fee.tax_rate == Decimal('19.00')
        assert o.total == Decimal('25.30')


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

    with scopes_disabled():
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

    with scopes_disabled():
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

    with scopes_disabled():
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
    with scopes_disabled():
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

    res['positions'] = [
        {
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
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.positions.first().positionid == 1
        assert o.positions.last().positionid == 2


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

    with scopes_disabled():
        question.options.create(answer="L")
    with scopes_disabled():
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
    with scopes_disabled():
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
    with scopes_disabled():
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
    with scopes_disabled():
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
    with scopes_disabled():
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
    with scopes_disabled():
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
    with scopes_disabled():
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
        {'non_field_errors': ['Date has wrong format. Use one of these formats instead: YYYY-MM-DD.']}]}]}

    question.type = Question.TYPE_DATETIME
    question.save()
    res['positions'][0]['answers'][0]['answer'] = '2018-05-14T13:00:00Z'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
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
    with scopes_disabled():
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

    res['force'] = True
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_order_create_quota_consume_cart(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk

    with scopes_disabled():
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
    with scopes_disabled():
        assert not CartPosition.objects.filter(pk=cr.pk).exists()


@pytest.mark.django_db
def test_order_create_quota_consume_cart_expired(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk

    with scopes_disabled():
        cr = CartPosition.objects.create(
            event=event, cart_id="uxLJBUMEcnxOLI2EuxLYN1hWJq9GKu4yWL9FEgs2m7M0vdFi@api", item=item,
            price=23,
            expires=now() - datetime.timedelta(hours=3)
        )

    quota.size = 0
    quota.save()
    res['consume_carts'] = [cr.cart_id]
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
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
    assert o.total == Decimal('0.00')
    assert o.status == Order.STATUS_PAID

    with scopes_disabled():
        p = o.payments.first()
    assert p.provider == "free"
    assert p.amount == o.total
    assert p.state == "confirmed"


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
    res['payment_date'] = '2019-04-01 08:20:00Z'
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert o.invoices.count() == 1

        p = o.payments.first()
    assert p.provider == "banktransfer"
    assert p.amount == o.total
    assert p.state == "confirmed"
    assert p.payment_date.year == 2019
    assert p.payment_date.month == 4
    assert p.payment_date.day == 1
    assert p.payment_date.hour == 8
    assert p.payment_date.minute == 20


@pytest.fixture
def seat(event, organizer, item):
    SeatingPlan.objects.create(
        name="Plan", organizer=organizer, layout="{}"
    )
    event.seat_category_mappings.create(
        layout_category='Stalls', product=item
    )
    return event.seats.create(name="A1", product=item, seat_guid="A1")


@pytest.mark.django_db
def test_order_create_with_seat(token_client, organizer, event, item, quota, seat, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['seat'] = seat.seat_guid
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.seat == seat


@pytest.mark.django_db
def test_order_create_with_blocked_seat_allowed(token_client, organizer, event, item, quota, seat, question):
    seat.blocked = True
    seat.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['seat'] = seat.seat_guid
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['sales_channel'] = 'bar'
    event.settings.seating_allow_blocked_seats_for_channel = ['bar']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_order_create_with_blocked_seat(token_client, organizer, event, item, quota, seat, question):
    seat.blocked = True
    seat.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['seat'] = seat.seat_guid
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'seat': ['The selected seat "A1" is not available.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_with_used_seat(token_client, organizer, event, item, quota, seat, question):
    CartPosition.objects.create(
        event=event, cart_id='aaa', item=item,
        price=21.5, expires=now() + datetime.timedelta(minutes=10), seat=seat
    )
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['seat'] = seat.seat_guid
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'seat': ['The selected seat "A1" is not available.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_with_unknown_seat(token_client, organizer, event, item, quota, seat, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['seat'] = seat.seat_guid + '_'
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'seat': ['The specified seat does not exist.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_require_seat(token_client, organizer, event, item, quota, seat, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'seat': ['The specified product requires to choose a seat.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_unseated(token_client, organizer, event, item, quota, seat, question):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        quota.items.add(item2)
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item2.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['seat'] = seat.seat_guid
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'seat': ['The specified product does not allow to choose a seat.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_with_duplicate_seat(token_client, organizer, event, item, quota, seat, question):
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
            "subevent": None,
            "seat": seat.seat_guid
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
            "subevent": None,
            "seat": seat.seat_guid
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
            {'seat': ['The selected seat "A1" is not available.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_with_seat_consumed_from_cart(token_client, organizer, event, item, quota, seat, question):
    CartPosition.objects.create(
        event=event, cart_id='aaa', item=item,
        price=21.5, expires=now() + datetime.timedelta(minutes=10), seat=seat
    )
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['seat'] = seat.seat_guid
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['consume_carts'] = ['aaa']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.seat == seat


@pytest.mark.django_db
def test_order_create_send_no_emails(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_order_create_send_emails(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['send_mail'] = True
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Your order: {}".format(resp.data['code'])


@pytest.mark.django_db
def test_order_create_send_emails_free(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['price'] = '0.00'
    res['payment_provider'] = 'free'
    del res['fees']
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['send_mail'] = True
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Your order: {}".format(resp.data['code'])


@pytest.mark.django_db
def test_order_create_send_emails_paid(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['send_mail'] = True
    res['status'] = 'p'
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    assert len(djmail.outbox) == 2
    assert djmail.outbox[0].subject == "Your order: {}".format(resp.data['code'])
    assert djmail.outbox[1].subject == "Payment received for your order: {}".format(resp.data['code'])


@pytest.mark.django_db
def test_order_paid_require_payment_method(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['payment_provider']
    res['status'] = 'p'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == [
        'You cannot create a paid order without a payment provider.'
    ]

    res['status'] = "n"
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        assert not o.payments.exists()


@pytest.mark.django_db
def test_order_create_auto_pricing(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.price == item.default_price
    assert o.total == item.default_price + Decimal('0.25')


@pytest.mark.django_db
def test_order_create_auto_pricing_reverse_charge(token_client, organizer, event, item, quota, question, taxrule):
    taxrule.eu_reverse_charge = True
    taxrule.home_country = Country('DE')
    taxrule.save()
    item.tax_rule = taxrule
    item.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['invoice_address']['country'] = 'FR'
    res['invoice_address']['is_business'] = True
    res['invoice_address']['vat_id'] = 'FR12345'
    res['invoice_address']['vat_id_validated'] = True
    del res['positions'][0]['price']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.price == Decimal('19.33')
    assert p.tax_rate == Decimal('0.00')
    assert p.tax_value == Decimal('0.00')
    assert o.total == Decimal('19.58')


@pytest.mark.django_db
def test_order_create_auto_pricing_reverse_charge_require_valid_vatid(token_client, organizer, event, item, quota,
                                                                      question, taxrule):
    taxrule.eu_reverse_charge = True
    taxrule.home_country = Country('DE')
    taxrule.save()
    item.tax_rule = taxrule
    item.save()
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['invoice_address']['country'] = 'FR'
    res['invoice_address']['is_business'] = True
    res['invoice_address']['vat_id'] = 'FR12345'
    del res['positions'][0]['price']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.price == Decimal('23.00')
    assert p.tax_rate == Decimal('19.00')


@pytest.mark.django_db
def test_order_create_autopricing_voucher_budget_partially(token_client, organizer, event, item, quota, question,
                                                           taxrule):
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=21.50, item=item, budget=Decimal('2.50'),
                                        max_usages=999)
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['voucher'] = voucher.code
    del res['positions'][0]['price']
    del res['positions'][0]['positionid']
    res['positions'].append(res['positions'][0])

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    print(resp.data)
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
        p2 = o.positions.last()
    assert p.price == Decimal('21.50')
    assert p2.price == Decimal('22.00')


@pytest.mark.django_db
def test_order_create_autopricing_voucher_budget_full(token_client, organizer, event, item, quota, question, taxrule):
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=21.50, item=item, budget=Decimal('0.50'),
                                        max_usages=999)
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['voucher'] = voucher.code
    del res['positions'][0]['price']
    del res['positions'][0]['positionid']
    res['positions'].append(res['positions'][0])

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'positions': [{}, {'voucher': ['The voucher has a remaining budget of 0.00, therefore a '
                                                        'discount of 1.50 can not be given.']}]}


@pytest.mark.django_db
def test_order_create_voucher_budget_exceeded(token_client, organizer, event, item, quota, question, taxrule):
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=21.50, item=item, budget=Decimal('3.00'),
                                        max_usages=999)
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['voucher'] = voucher.code
    res['positions'][0]['price'] = '19.00'
    del res['positions'][0]['positionid']

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    print(resp.data)
    assert resp.status_code == 400
    assert resp.data == {'positions': [{'voucher': ['The voucher has a remaining budget of 3.00, therefore a '
                                                    'discount of 4.00 can not be given.']}]}


@pytest.mark.django_db
def test_order_create_voucher_price(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=15, item=item)
    res['positions'][0]['voucher'] = voucher.code
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        o = Order.objects.get(code=resp.data['code'])
        p = o.positions.first()
    assert p.voucher == voucher
    voucher.refresh_from_db()
    assert voucher.redeemed == 1
    assert p.price == Decimal('15.00')
    assert o.total == Decimal('15.25')


@pytest.mark.django_db
def test_order_create_voucher_unknown_code(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    with scopes_disabled():
        event.vouchers.create(price_mode="set", value=15, item=item)
    res['positions'][0]['voucher'] = "FOOBAR"
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'voucher': ['Object with code=FOOBAR does not exist.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_voucher_redeemed(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    del res['positions'][0]['price']
    res['positions'][0]['answers'][0]['question'] = question.pk
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=15, item=item, redeemed=1)
    res['positions'][0]['voucher'] = voucher.code
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'voucher': ['The voucher has already been used the maximum number of times.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_voucher_redeemed_partially(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['answers'][0]['question'] = question.pk
    res['positions'][0]['item'] = item.pk
    del res['positions'][0]['price']
    del res['positions'][0]['positionid']
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=15, item=item, redeemed=1, max_usages=2)
    res['positions'][0]['voucher'] = voucher.code
    res['positions'].append(copy.copy(res['positions'][0]))
    res['positions'].append(copy.copy(res['positions'][0]))
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {},
            {'voucher': ['The voucher has already been used the maximum number of times.']},
            {'voucher': ['The voucher has already been used the maximum number of times.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_voucher_item_mismatch(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        voucher = event.vouchers.create(price_mode="set", value=15, item=item2, redeemed=0)
    res['positions'][0]['voucher'] = voucher.code
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'voucher': ['This voucher is not valid for this product.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_voucher_expired(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=15, item=item, redeemed=0,
                                        valid_until=now() - datetime.timedelta(days=1))
    res['positions'][0]['voucher'] = voucher.code
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'positions': [
            {'voucher': ['This voucher is expired.']},
        ]
    }


@pytest.mark.django_db
def test_order_create_voucher_block_quota(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(ORDER_CREATE_PAYLOAD)
    res['positions'][0]['item'] = item.pk
    res['positions'][0]['answers'][0]['question'] = question.pk
    del res['positions'][0]['price']
    quota.size = 0
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400

    with scopes_disabled():
        voucher = event.vouchers.create(price_mode="set", value=15, item=item, redeemed=0,
                                        block_quota=True)
    res['positions'][0]['voucher'] = voucher.code
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201


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
    with scopes_disabled():
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
    res['mark_canceled'] = True
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/refunds/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data=res
    )
    assert resp.status_code == 201
    with scopes_disabled():
        r = order.refunds.get(local_id=resp.data['local_id'])
    assert r.provider == "manual"
    assert r.amount == Decimal("23.00")
    assert r.state == "created"
    assert r.source == "admin"
    assert r.info_data == {"foo": "bar"}
    assert r.payment.local_id == 2
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELED


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
    with scopes_disabled():
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


@pytest.mark.django_db
def test_order_delete(token_client, organizer, event, order):
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_order_delete_test_mode(token_client, organizer, event, order):
    order.testmode = True
    order.save()
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert not Order.objects.filter(code=order.code).exists()


@pytest.mark.django_db
def test_order_delete_test_mode_voucher(token_client, organizer, event, order, item):
    order.testmode = True
    order.save()
    with scopes_disabled():
        q = event.quotas.create(name="Quota")
        q.items.add(item)
        voucher = event.vouchers.create(price_mode="set", value=15, quota=q, redeemed=1)
        op = order.positions.first()
        op.voucher = voucher
        op.save()

    assert voucher.redeemed == 1

    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert not Order.objects.filter(code=order.code).exists()
    voucher.refresh_from_db()
    assert voucher.redeemed == 0


@pytest.mark.django_db
def test_order_delete_test_mode_voucher_cancelled_position(token_client, organizer, event, order, item):
    order.testmode = True
    order.save()
    with scopes_disabled():
        q = event.quotas.create(name="Quota")
        q.items.add(item)
        voucher = event.vouchers.create(price_mode="set", value=15, quota=q, redeemed=42)
        op = order.all_positions.last()
        op.voucher = voucher
        op.save()

    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert not Order.objects.filter(code=order.code).exists()
    voucher.refresh_from_db()
    assert voucher.redeemed == 42


@pytest.mark.django_db
def test_order_delete_test_mode_voucher_cancelled_order(token_client, organizer, event, order, item):
    with scopes_disabled():
        order.testmode = True
        order.status = Order.STATUS_CANCELED
        order.save()
        q = event.quotas.create(name="Quota")
        q.items.add(item)
        voucher = event.vouchers.create(price_mode="set", value=15, quota=q, redeemed=42)
        op = order.positions.first()
        op.voucher = voucher
        op.save()

    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        )
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert not Order.objects.filter(code=order.code).exists()
    voucher.refresh_from_db()
    assert voucher.redeemed == 42


@pytest.mark.django_db
def test_order_update_ignore_fields(token_client, organizer, event, order):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'status': 'c'
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == 'n'


@pytest.mark.django_db
def test_order_update_only_partial(token_client, organizer, event, order):
    resp = token_client.put(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'status': 'c'
        }
    )
    assert resp.status_code == 405


@pytest.mark.django_db
def test_order_update_state_validation(token_client, organizer, event, order):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'invoice_address': {
                "is_business": False,
                "company": "This is my company name",
                "name": "John Doe",
                "name_parts": {},
                "street": "",
                "state": "",
                "zipcode": "",
                "city": "Paris",
                "country": "NONEXISTANT",
                "internal_reference": "",
                "vat_id": "",
            }
        }
    )
    assert resp.status_code == 400
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'invoice_address': {
                "is_business": False,
                "company": "This is my company name",
                "name": "John Doe",
                "name_parts": {},
                "street": "",
                "state": "NONEXISTANT",
                "zipcode": "",
                "city": "Test",
                "country": "AU",
                "internal_reference": "",
                "vat_id": "",
            }
        }
    )
    assert resp.status_code == 400

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'invoice_address': {
                "is_business": False,
                "company": "This is my company name",
                "name": "John Doe",
                "name_parts": {},
                "street": "",
                "state": "QLD",
                "zipcode": "",
                "city": "Test",
                "country": "AU",
                "internal_reference": "",
                "vat_id": "",
            }
        }
    )
    assert resp.status_code == 200
    order.invoice_address.refresh_from_db()
    assert order.invoice_address.state == "QLD"
    assert order.invoice_address.country == "AU"


@pytest.mark.django_db
def test_order_update_allowed_fields(token_client, organizer, event, order):
    event.settings.locales = ['de', 'en']
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'comment': 'Here is a comment',
            'checkin_attention': True,
            'email': 'foo@bar.com',
            'locale': 'de',
            'invoice_address': {
                "is_business": False,
                "company": "This is my company name",
                "name": "John Doe",
                "name_parts": {},
                "street": "",
                "state": "",
                "zipcode": "",
                "city": "Paris",
                "country": "FR",
                "internal_reference": "",
                "vat_id": "",
            }
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.comment == 'Here is a comment'
    assert order.checkin_attention
    assert order.email == 'foo@bar.com'
    assert order.locale == 'de'
    assert order.invoice_address.company == "This is my company name"
    assert order.invoice_address.name_cached == "John Doe"
    assert order.invoice_address.name_parts == {'_legacy': 'John Doe'}
    assert str(order.invoice_address.country) == "FR"
    assert not order.invoice_address.vat_id_validated
    assert order.invoice_address.city == "Paris"
    with scopes_disabled():
        assert order.all_logentries().get(action_type='pretix.event.order.comment')
        assert order.all_logentries().get(action_type='pretix.event.order.checkin_attention')
        assert order.all_logentries().get(action_type='pretix.event.order.contact.changed')
        assert order.all_logentries().get(action_type='pretix.event.order.locale.changed')
        assert order.all_logentries().get(action_type='pretix.event.order.modified')


@pytest.mark.django_db
def test_order_update_validated_vat_id(token_client, organizer, event, order):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'invoice_address': {
                "is_business": False,
                "company": "This is my company name",
                "name": "John Doe",
                "name_parts": {},
                "street": "",
                "state": "",
                "zipcode": "",
                "city": "Paris",
                "country": "FR",
                "internal_reference": "",
                "vat_id": "FR123",
                "vat_id_validated": True
            }
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.invoice_address.vat_id == "FR123"
    assert order.invoice_address.vat_id_validated


@pytest.mark.django_db
def test_order_update_invoiceaddress_delete_create(token_client, organizer, event, order):
    event.settings.locales = ['de', 'en']
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'invoice_address': None,
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    with pytest.raises(InvoiceAddress.DoesNotExist):
        order.invoice_address

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'invoice_address': {
                "is_business": False,
                "company": "This is my company name",
                "name": "",
                "name_parts": {},
                "street": "",
                "state": "",
                "zipcode": "",
                "city": "Paris",
                "country": "Fr",
                "internal_reference": "",
                "vat_id": "",
            }
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.invoice_address.company == "This is my company name"
    assert str(order.invoice_address.country) == "FR"
    assert order.invoice_address.city == "Paris"


@pytest.mark.django_db
def test_order_update_email_to_none(token_client, organizer, event, order):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'email': None,
        }
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.email is None


@pytest.mark.django_db
def test_order_update_locale_to_invalid(token_client, organizer, event, order):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/orders/{}/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={
            'locale': 'de',
        }
    )
    assert resp.status_code == 400
    assert resp.data == {'locale': ['"de" is not a supported locale for this event.']}


@pytest.mark.django_db
def test_order_create_invoice(token_client, organizer, event, order):
    event.settings.invoice_generate = 'True'

    event.settings.invoice_generate_sales_channels = []

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/create_invoice/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.status_code == 400

    event.settings.invoice_generate_sales_channels = ['web']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/create_invoice/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.status_code == 201
    assert resp.data == {
        'order': 'FOO',
        'number': 'DUMMY-00001',
        'is_cancellation': False,
        'invoice_from': '',
        'invoice_to': 'Sample company\nNew Zealand\nVAT-ID: DE123',
        'date': now().date().isoformat(),
        'refers': None,
        'locale': 'en',
        'introductory_text': '',
        'additional_text': '',
        'payment_provider_text': '',
        'footer_text': '',
        'lines': [
            {
                'position': 1,
                'description': 'Budget Ticket<br />Attendee: Peter',
                'gross_value': '23.00',
                'tax_value': '0.00',
                'tax_rate': '0.00',
                'tax_name': ''
            },
            {
                'position': 2,
                'description': 'Payment fee',
                'gross_value': '0.25',
                'tax_value': '0.05',
                'tax_rate': '19.00',
                'tax_name': ''
            }
        ],
        'foreign_currency_display': None,
        'foreign_currency_rate': None,
        'foreign_currency_rate_date': None,
        'internal_reference': ''
    }

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/create_invoice/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.data == {'detail': 'An invoice for this order already exists.'}
    assert resp.status_code == 400

    event.settings.invoice_generate = 'False'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/create_invoice/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.status_code == 400
    assert resp.data == {'detail': 'You cannot generate an invoice for this order.'}


@pytest.mark.django_db
def test_order_regenerate_secrets(token_client, organizer, event, order):
    s = order.secret
    with scopes_disabled():
        ps = order.positions.first().secret
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/regenerate_secrets/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert s != order.secret
    with scopes_disabled():
        assert ps != order.positions.first().secret


@pytest.mark.django_db
def test_order_resend_link(token_client, organizer, event, order):
    djmail.outbox = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/resend_link/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.status_code == 204
    assert len(djmail.outbox) == 1

    order.email = None
    order.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/resend_link/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', data={}
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_orderposition_price_calculation(token_client, organizer, event, order, item):
    with scopes_disabled():
        op = order.positions.first()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('23.00'),
        'gross_formatted': '23.00',
        'name': '',
        'net': Decimal('23.00'),
        'rate': Decimal('0.00'),
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_item_with_tax(token_client, organizer, event, order, item, taxrule):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23, tax_rule=taxrule)
        op = order.positions.first()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('23.00'),
        'gross_formatted': '23.00',
        'name': '',
        'net': Decimal('19.33'),
        'rate': Decimal('19.00'),
        'tax': Decimal('3.67')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_item_with_variation(token_client, organizer, event, order):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        var = item2.variations.create(default_price=12, value="XS")
        op = order.positions.first()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
            'variation': var.pk
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('12.00'),
        'gross_formatted': '12.00',
        'name': '',
        'net': Decimal('12.00'),
        'rate': Decimal('0.00'),
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_subevent(token_client, organizer, event, order, subevent):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        op = order.positions.first()
    op.subevent = subevent
    op.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
            'subevent': subevent.pk
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('23.00'),
        'gross_formatted': '23.00',
        'name': '',
        'net': Decimal('23.00'),
        'rate': Decimal('0.00'),
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_subevent_with_override(token_client, organizer, event, order, subevent):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        se2 = event.subevents.create(name="Foobar", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC))
        se2.subeventitem_set.create(item=item2, price=12)
        op = order.positions.first()
    op.subevent = subevent
    op.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
            'subevent': se2.pk
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('12.00'),
        'gross_formatted': '12.00',
        'name': '',
        'net': Decimal('12.00'),
        'rate': Decimal('0.00'),
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_voucher_matching(token_client, organizer, event, order, subevent, item):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        q = event.quotas.create(name="Quota")
        q.items.add(item)
        q.items.add(item2)
        voucher = event.vouchers.create(price_mode="set", value=15, quota=q)
        op = order.positions.first()
    op.voucher = voucher
    op.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('15.00'),
        'gross_formatted': '15.00',
        'name': '',
        'net': Decimal('15.00'),
        'rate': Decimal('0.00'),
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_voucher_not_matching(token_client, organizer, event, order, subevent, item):
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=23)
        q = event.quotas.create(name="Quota")
        q.items.add(item)
        voucher = event.vouchers.create(price_mode="set", value=15, quota=q)
        op = order.positions.first()
    op.voucher = voucher
    op.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('23.00'),
        'gross_formatted': '23.00',
        'name': '',
        'net': Decimal('23.00'),
        'rate': Decimal('0.00'),
        'tax': Decimal('0.00')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_net_price(token_client, organizer, event, order, subevent, item, taxrule):
    taxrule.price_includes_tax = False
    taxrule.save()
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=10, tax_rule=taxrule)
        op = order.positions.first()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('11.90'),
        'gross_formatted': '11.90',
        'name': '',
        'net': Decimal('10.00'),
        'rate': Decimal('19.00'),
        'tax': Decimal('1.90')
    }


@pytest.mark.django_db
def test_orderposition_price_calculation_reverse_charge(token_client, organizer, event, order, subevent, item, taxrule):
    taxrule.price_includes_tax = False
    taxrule.eu_reverse_charge = True
    taxrule.home_country = Country('DE')
    taxrule.save()
    order.invoice_address.is_business = True
    order.invoice_address.vat_id = 'ATU1234567'
    order.invoice_address.vat_id_validated = True
    order.invoice_address.country = Country('AT')
    order.invoice_address.save()
    with scopes_disabled():
        item2 = event.items.create(name="Budget Ticket", default_price=10, tax_rule=taxrule)
        op = order.positions.first()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orderpositions/{}/price_calc/'.format(organizer.slug, event.slug, op.pk),
        data={
            'item': item2.pk,
        }
    )
    assert resp.status_code == 200
    assert resp.data == {
        'gross': Decimal('10.00'),
        'gross_formatted': '10.00',
        'name': '',
        'net': Decimal('10.00'),
        'rate': Decimal('0.00'),
        'tax': Decimal('0.00')
    }
