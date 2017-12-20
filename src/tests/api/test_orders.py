import datetime
from decimal import Decimal
from distutils.version import LooseVersion
from unittest import mock

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_countries.fields import Country
from pytz import UTC

from pretix import __version__
from pretix.base.models import InvoiceAddress, Order, OrderPosition
from pretix.base.models.orders import OrderFee
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice,
)


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def taxrule(event):
    return event.tax_rules.create(rate=Decimal('19.00'))


@pytest.fixture
def quota(event, item):
    q = event.quotas.create(name="Budget Quota", size=200)
    q.items.add(item)
    return q


@pytest.fixture
def order(event, item, taxrule):
    testtime = datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, secret="k24fiuwvu8kxz3y1",
            datetime=datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC),
            expires=datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=UTC),
            total=23, payment_provider='banktransfer', locale='en'
        )
        o.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.25'), tax_rate=Decimal('19.00'),
                      tax_value=Decimal('0.05'), tax_rule=taxrule)
        InvoiceAddress.objects.create(order=o, company="Sample company", country=Country('NZ'))
        OrderPosition.objects.create(
            order=o,
            item=item,
            variation=None,
            price=Decimal("23"),
            attendee_name="Peter",
            secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w"
        )
        return o


TEST_ORDERPOSITION_RES = {
    "id": 1,
    "order": "FOO",
    "positionid": 1,
    "item": 1,
    "variation": None,
    "price": "23.00",
    "attendee_name": "Peter",
    "attendee_email": None,
    "voucher": None,
    "tax_rate": "0.00",
    "tax_value": "0.00",
    "tax_rule": None,
    "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
    "addon_to": None,
    "checkins": [],
    "downloads": [],
    "answers": [],
    "subevent": None
}
TEST_ORDER_RES = {
    "code": "FOO",
    "status": "n",
    "secret": "k24fiuwvu8kxz3y1",
    "email": "dummy@dummy.test",
    "locale": "en",
    "datetime": "2017-12-01T10:00:00Z",
    "expires": "2017-12-10T10:00:00Z",
    "payment_date": None,
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
    "payment_fee": "0.25",
    "payment_fee_tax_rate": "19.00",
    "payment_fee_tax_value": "0.05",
    "total": "23.00",
    "comment": "",
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
    "positions": [TEST_ORDERPOSITION_RES],
    "downloads": []
}


@pytest.mark.django_db
@pytest.mark.xfail(
    LooseVersion(__version__) >= LooseVersion("1.9.0.dev0"),
    reason="Deprecated attributes payment_fee_* should be removed by now",
)
def test_order_list(token_client, organizer, event, order, item, taxrule):
    res = dict(TEST_ORDER_RES)
    res["positions"][0]["id"] = order.positions.first().pk
    res["positions"][0]["item"] = item.pk
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


@pytest.mark.django_db
def test_order_detail(token_client, organizer, event, order, item, taxrule):
    res = dict(TEST_ORDER_RES)
    res["positions"][0]["id"] = order.positions.first().pk
    res["positions"][0]["item"] = item.pk
    res["fees"][0]["tax_rule"] = taxrule.pk
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


@pytest.mark.django_db
def test_orderposition_list(token_client, organizer, event, order, item, subevent):
    var = item.variations.create(value="Children")
    res = dict(TEST_ORDERPOSITION_RES)
    op = order.positions.first()
    op.variation = var
    op.save()
    res["id"] = op.pk
    res["item"] = item.pk
    res["variation"] = var.pk

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
        '/api/v1/organizers/{}/events/{}/orderpositions/?item={}'.format(organizer.slug, event.slug, item.pk + 1))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?variation={}'.format(organizer.slug, event.slug, var.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?variation={}'.format(organizer.slug, event.slug, var.pk + 1))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/orderpositions/?attendee_name=Peter'.format(organizer.slug, event.slug))
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
        '/api/v1/organizers/{}/events/{}/orderpositions/?subevent={}'.format(organizer.slug, event.slug,
                                                                             subevent.pk + 1))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_orderposition_detail(token_client, organizer, event, order, item):
    res = dict(TEST_ORDERPOSITION_RES)
    op = order.positions.first()
    res["id"] = op.pk
    res["item"] = item.pk
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
