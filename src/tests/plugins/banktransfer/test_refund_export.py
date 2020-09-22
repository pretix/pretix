import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now

from pretix.base.models import Event, Order, OrderRefund, Organizer, Team, User
from pretix.plugins.banktransfer.models import RefundExport
from pretix.plugins.banktransfer.views import (
    _row_key_func, _unite_transaction_rows,
)


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
    order = Order.objects.create(
        code='1Z3AS', event=event, email='admin@localhost',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23
    )
    refund = OrderRefund.objects.create(
        order=order,
        amount=Decimal("23"),
        provider='banktransfer',
        state=OrderRefund.REFUND_STATE_CREATED,
        info=json.dumps({
            'payer': "Abc Def",
            'iban': "DE27520521540534534466",
            'bic': "HELADEF1MEG",
        })
    )
    return event, user, refund


url_prefixes = [
    "/control/event/dummy/dummy/",
    "/control/organizer/dummy/"
]


@pytest.mark.django_db
@pytest.mark.parametrize("url_prefix", url_prefixes)
def test_export_refunds_as_sepa_xml(client, env, url_prefix):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post(f'{url_prefix}banktransfer/refunds/', {"unite_transactions": True}, follow=True)
    assert b"SEPA" in r.content
    r = client.get(f'{url_prefix}banktransfer/sepa-export/1/')
    assert r.status_code == 200
    r = client.post(f'{url_prefix}banktransfer/sepa-export/1/', {
        "account_holder": "Fission Festival",
        "iban": "DE71720690050653667120",
        "bic": "GENODEF1AIL",
    })
    assert "DE27520521540534534466" in "".join(str(part) for part in r.streaming_content)


@pytest.mark.django_db
@pytest.mark.parametrize("url_prefix", url_prefixes)
def test_export_refunds(client, env, url_prefix):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.get(f'{url_prefix}banktransfer/refunds/')
    assert r.status_code == 200
    r = client.post(f'{url_prefix}banktransfer/refunds/', {"unite_transactions": True}, follow=True)
    assert r.status_code == 200
    assert RefundExport.objects.exists()
    assert b"Download CSV" in r.content
    r = client.get(f'{url_prefix}banktransfer/export/1/')
    assert r.status_code == 200
    assert "DE27520521540534534466" in "".join(str(part) for part in r.streaming_content)


def test_unite_transaction_rows():
    rows = sorted([
        {
            'payer': "Abc Def",
            'iban': 'DE12345678901234567890',
            'bic': 'HARKE9000',
            'id': "ROLLA-R-1",
            'amount': Decimal("42.23"),
        },
        {
            'payer': "First Last",
            'iban': 'DE111111111111111111111',
            'bic': 'ikswez2020',
            'id': "PARTY-R-1",
            'amount': Decimal("6.50"),
        }
    ], key=_row_key_func)

    assert _unite_transaction_rows(rows) == rows

    rows = sorted(rows + [
        {
            'payer': "Abc Def",
            'iban': 'DE12345678901234567890',
            'bic': 'HARKE9000',
            'id': "ROLLA-R-1",
            'amount': Decimal("7.77"),
        },
        {
            'payer': "Another Last",
            'iban': 'DE111111111111111111111',
            'bic': 'ikswez2020',
            'id': "PARTY-R-2",
            'amount': Decimal("13.50"),
        }
    ], key=_row_key_func)

    assert _unite_transaction_rows(rows) == sorted([
        {
            'payer': "Abc Def",
            'iban': 'DE12345678901234567890',
            'bic': 'HARKE9000',
            'id': "ROLLA-R-1",
            'amount': Decimal("50.00"),
        },
        {
            'payer': 'Another Last, First Last',
            'iban': 'DE111111111111111111111',
            'bic': 'ikswez2020',
            'id': 'PARTY-R-1, PARTY-R-2',
            'amount': Decimal('20.00'),
        }], key=_row_key_func)
