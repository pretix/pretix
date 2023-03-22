#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
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


@pytest.fixture
def refund_huf(env):
    event = Event.objects.create(
        organizer=env[0].organizer, name='Dummy', slug='dummy2', currency='HUF',
        date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.paypal'
    )
    order = Order.objects.create(
        code='1Z3AS', event=event, email='admin@localhost',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=42
    )
    refund = OrderRefund.objects.create(
        order=order,
        amount=Decimal("42"),
        provider='banktransfer',
        state=OrderRefund.REFUND_STATE_CREATED,
        info=json.dumps({
            'payer': "Abc Def",
            'iban': "DE27520521540534534466",
            'bic': "HELADEF1MEG",
        })
    )
    return refund


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
    r = client.get(f'{url_prefix}banktransfer/sepa-export/{RefundExport.objects.last().id}/')
    assert r.status_code == 200
    r = client.post(f'{url_prefix}banktransfer/sepa-export/{RefundExport.objects.last().id}/', {
        "account_holder": "Fission Festival",
        "iban": "DE71720690050653667120",
        "bic": "GENODEF1AIL",
    })
    r = "".join(str(part) for part in r.streaming_content)
    assert "DE27520521540534534466" in r
    assert "HELADEF" in r


@pytest.mark.django_db
@pytest.mark.parametrize("url_prefix", url_prefixes)
def test_export_refunds(client, env, url_prefix):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.get(f'{url_prefix}banktransfer/refunds/')
    assert r.status_code == 200
    r = client.post(f'{url_prefix}banktransfer/refunds/', {"unite_transactions": True}, follow=True)
    assert r.status_code == 200
    refund = RefundExport.objects.last()
    assert refund is not None
    assert b"Download CSV" in r.content
    r = client.get(f'{url_prefix}banktransfer/export/{refund.id}/')
    assert r.status_code == 200
    r = "".join(str(part) for part in r.streaming_content)
    assert "DE27520521540534534466" in r
    assert "HELADEF" in r


@pytest.mark.django_db
def test_export_refunds_multi_currency(client, env, refund_huf):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.get('/control/organizer/dummy/banktransfer/refunds/')
    assert r.status_code == 200
    r = client.post('/control/organizer/dummy/banktransfer/refunds/', {"unite_transactions": True}, follow=True)
    assert r.status_code == 200
    assert RefundExport.objects.count() == 2
    assert RefundExport.objects.get(currency="EUR").sum == Decimal("23.00")
    assert RefundExport.objects.get(currency="HUF").sum == Decimal("42.00")


@pytest.mark.django_db
@pytest.mark.parametrize("url_prefix", url_prefixes)
def test_export_refunds_omit_invalid_bic(client, env, url_prefix):
    d = env[2].info_data
    d['bic'] = 'TROLOLO'
    env[2].info = json.dumps(d)
    env[2].save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.get(f'{url_prefix}banktransfer/refunds/')
    assert r.status_code == 200
    r = client.post(f'{url_prefix}banktransfer/refunds/', {"unite_transactions": True}, follow=True)
    assert r.status_code == 200
    refund = RefundExport.objects.last()
    assert refund is not None
    assert b"Download CSV" in r.content
    r = client.get(f'{url_prefix}banktransfer/export/{refund.id}/')
    assert r.status_code == 200
    r = "".join(str(part) for part in r.streaming_content)
    assert "DE27520521540534534466" in r
    assert "TROLOLO" not in r
    assert "HELADEF" not in r
    r = client.post(f'{url_prefix}banktransfer/sepa-export/{refund.id}/', {
        "account_holder": "Fission Festival",
        "iban": "DE71720690050653667120",
        "bic": "GENODEF1AIL",
    })
    assert r.status_code == 200
    r = "".join(str(part) for part in r.streaming_content)
    assert "DE27520521540534534466" in r
    assert "TROLOLO" not in r


def test_unite_transaction_rows():
    rows = sorted([
        {
            'payer': "Abc Def",
            'iban': 'DE12345678901234567890',
            'bic': 'HARKE9000',
            'id': "ROLLA-R-1",
            'comment': None,
            'amount': Decimal("42.23"),
        },
        {
            'payer': "First Last",
            'iban': 'DE111111111111111111111',
            'bic': 'ikswez2020',
            'id': "PARTY-R-1",
            'comment': None,
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
            'comment': None,
            'amount': Decimal("7.77"),
        },
        {
            'payer': "Another Last",
            'iban': 'DE111111111111111111111',
            'bic': 'ikswez2020',
            'id': "PARTY-R-2",
            'comment': None,
            'amount': Decimal("13.50"),
        }
    ], key=_row_key_func)

    assert _unite_transaction_rows(rows) == sorted([
        {
            'payer': "Abc Def",
            'iban': 'DE12345678901234567890',
            'bic': 'HARKE9000',
            'id': "ROLLA-R-1",
            'comment': None,
            'amount': Decimal("50.00"),
        },
        {
            'payer': 'Another Last, First Last',
            'iban': 'DE111111111111111111111',
            'bic': 'ikswez2020',
            'id': 'PARTY-R-1, PARTY-R-2',
            'comment': None,
            'amount': Decimal('20.00'),
        }], key=_row_key_func)
