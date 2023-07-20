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
import copy
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import GiftCard, Order, Organizer


@pytest.fixture
def giftcard(organizer, event):
    gc = organizer.issued_gift_cards.create(secret="ABCDEF", currency="EUR")
    gc.transactions.create(value=Decimal('23.00'), acceptor=organizer)
    return gc


@pytest.fixture
def other_giftcard(organizer, event):
    o = Organizer.objects.create(name='Dummy2', slug='dummy2')
    organizer.gift_card_issuer_acceptance.create(issuer=o)
    gc = o.issued_gift_cards.create(secret="GHIJK", currency="EUR")
    return gc


TEST_GC_RES = {
    "id": 1,
    "secret": "ABCDEF",
    "value": "23.00",
    "testmode": False,
    "expires": None,
    "conditions": None,
    "currency": "EUR",
    "issuer": "dummy",
    "owner_ticket": None
}


@pytest.mark.django_db
def test_giftcard_list(token_client, organizer, event, giftcard, other_giftcard):
    res = dict(TEST_GC_RES)
    res["id"] = giftcard.pk
    res["issuance"] = giftcard.issuance.isoformat().replace('+00:00', 'Z')

    resp = token_client.get('/api/v1/organizers/{}/giftcards/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/giftcards/?testmode=true'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/giftcards/?testmode=false'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/giftcards/?secret=DEF'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/giftcards/?secret=ABCDEF'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/giftcards/?include_accepted=true'.format(organizer.slug))
    assert resp.status_code == 200
    assert 2 == len(resp.data['results'])


@pytest.mark.django_db
def test_giftcard_detail(token_client, organizer, event, giftcard):
    res = dict(TEST_GC_RES)
    res["id"] = giftcard.pk
    res["issuance"] = giftcard.issuance.isoformat().replace('+00:00', 'Z')
    resp = token_client.get('/api/v1/organizers/{}/giftcards/{}/'.format(organizer.slug, giftcard.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_giftcard_detail_expand(token_client, organizer, event, giftcard):
    with scopes_disabled():
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, datetime=now(), expires=now() + timedelta(days=10),
            total=14, locale='en'
        )
        ticket = event.items.create(name='Early-bird ticket', category=None, default_price=23, admission=True,
                                    personalized=True)
        op = o.positions.create(item=ticket, price=Decimal("14"))
        giftcard.owner_ticket = op
        giftcard.save()

    res = dict(TEST_GC_RES)
    res["id"] = giftcard.pk
    res["issuance"] = giftcard.issuance.isoformat().replace('+00:00', 'Z')
    resp = token_client.get('/api/v1/organizers/{}/giftcards/{}/?expand=owner_ticket'.format(organizer.slug, giftcard.pk))
    assert resp.status_code == 200

    assert resp.data["owner_ticket"] == {
        "id": op.pk,
        "order": {"code": "FOO", "event": "dummy"},
        "positionid": op.positionid,
        "item": ticket.pk,
        "variation": None,
        "price": "14.00",
        "attendee_name": None,
        "attendee_name_parts": {},
        "company": None,
        "street": None,
        "zipcode": None,
        "city": None,
        "country": None,
        "state": None,
        "discount": None,
        "attendee_email": None,
        "voucher": None,
        "tax_rate": "0.00",
        "tax_value": "0.00",
        "secret": op.secret,
        "addon_to": None,
        "subevent": None,
        "checkins": [],
        "downloads": [],
        "answers": [],
        "tax_rule": None,
        "pseudonymization_id": op.pseudonymization_id,
        "pdf_data": {},
        "seat": None,
        "canceled": False,
        "valid_from": None,
        "valid_until": None,
        "blocked": None
    }


TEST_GIFTCARD_CREATE_PAYLOAD = {
    "secret": "DEFABC",
    "value": "12.00",
    "testmode": False,
    "currency": "EUR",
}


@pytest.mark.django_db
def test_giftcard_create(token_client, organizer, event):
    resp = token_client.post(
        '/api/v1/organizers/{}/giftcards/'.format(organizer.slug),
        TEST_GIFTCARD_CREATE_PAYLOAD,
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        gc = GiftCard.objects.get(pk=resp.data['id'])
        assert gc.issuer == organizer
        assert gc.value == Decimal('12.00')


@pytest.mark.django_db
def test_giftcard_duplicate_secert(token_client, organizer, event, giftcard):
    res = copy.copy(TEST_GIFTCARD_CREATE_PAYLOAD)
    res['secret'] = 'ABCDEF'
    resp = token_client.post(
        '/api/v1/organizers/{}/giftcards/'.format(organizer.slug),
        res,
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {'secret': ['A gift card with the same secret already exists in your or an affiliated organizer account.']}


@pytest.mark.django_db
def test_giftcard_patch_owner_by_id(token_client, organizer, event, giftcard):
    with scopes_disabled():
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, datetime=now(), expires=now() + timedelta(days=10),
            total=14, locale='en'
        )
        ticket = event.items.create(name='Early-bird ticket', category=None, default_price=23, admission=True,
                                    personalized=True)
        op = o.positions.create(item=ticket, price=Decimal("14"))

    resp = token_client.patch(
        '/api/v1/organizers/{}/giftcards/{}/'.format(organizer.slug, giftcard.pk),
        {
            'owner_ticket': op.pk,
        },
        format='json'
    )
    assert resp.status_code == 200
    giftcard.refresh_from_db()
    assert giftcard.owner_ticket == op


@pytest.mark.django_db
def test_giftcard_patch_owner_by_secret(token_client, organizer, event, giftcard):
    with scopes_disabled():
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, datetime=now(), expires=now() + timedelta(days=10),
            total=14, locale='en'
        )
        ticket = event.items.create(name='Early-bird ticket', category=None, default_price=23, admission=True,
                                    personalized=True)
        op = o.positions.create(item=ticket, price=Decimal("14"))

    resp = token_client.patch(
        '/api/v1/organizers/{}/giftcards/{}/'.format(organizer.slug, giftcard.pk),
        {
            'owner_ticket': op.secret,
        },
        format='json'
    )
    assert resp.status_code == 200
    giftcard.refresh_from_db()
    assert giftcard.owner_ticket == op


@pytest.mark.django_db
def test_giftcard_patch_min_value(token_client, organizer, event, giftcard):
    resp = token_client.patch(
        '/api/v1/organizers/{}/giftcards/{}/'.format(organizer.slug, giftcard.pk),
        {
            'value': '-10.00',
        },
        format='json'
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_giftcard_transact(token_client, organizer, event, giftcard):
    resp = token_client.post(
        '/api/v1/organizers/{}/giftcards/{}/transact/'.format(organizer.slug, giftcard.pk),
        {
            'value': '10.00',
        },
        format='json'
    )
    assert resp.status_code == 200
    giftcard.refresh_from_db()
    assert giftcard.value == Decimal('33.00')
    resp = token_client.post(
        '/api/v1/organizers/{}/giftcards/{}/transact/'.format(organizer.slug, giftcard.pk),
        {
            'value': '10.00',
            'text': 'bla',
            'info': {"a": "b"}
        },
        format='json'
    )
    assert resp.status_code == 200
    giftcard.refresh_from_db()
    assert giftcard.value == Decimal('43.00')
    assert giftcard.transactions.last().text == 'bla'
    assert giftcard.transactions.last().info == {"a": "b"}
    assert giftcard.transactions.last().acceptor == organizer


@pytest.mark.django_db
def test_giftcard_transact_cross_organizer(token_client, organizer, event, other_giftcard):
    resp = token_client.post(
        '/api/v1/organizers/{}/giftcards/{}/transact/?include_accepted=true'.format(organizer.slug, other_giftcard.pk),
        {
            'value': '10.00',
        },
        format='json'
    )
    assert resp.status_code == 200
    other_giftcard.refresh_from_db()
    assert other_giftcard.value == Decimal('10.00')
    assert other_giftcard.transactions.last().acceptor == organizer


@pytest.mark.django_db
def test_giftcard_transact_cross_organizer_inactive(token_client, organizer, event, other_giftcard):
    organizer.gift_card_issuer_acceptance.update(active=False)
    resp = token_client.post(
        '/api/v1/organizers/{}/giftcards/{}/transact/?include_accepted=true'.format(organizer.slug, other_giftcard.pk),
        {
            'value': '10.00',
        },
        format='json'
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_giftcard_transact_min_zero(token_client, organizer, event, giftcard):
    resp = token_client.post(
        '/api/v1/organizers/{}/giftcards/{}/transact/'.format(organizer.slug, giftcard.pk),
        {
            'value': '-100.00',
        },
        format='json'
    )
    assert resp.status_code == 409
    assert resp.data == {'value': ['The gift card does not have sufficient credit for this operation.']}
    giftcard.refresh_from_db()
    assert giftcard.value == Decimal('23.00')


@pytest.mark.django_db
def test_giftcard_no_deletion(token_client, organizer, event, giftcard):
    resp = token_client.delete(
        '/api/v1/organizers/{}/giftcards/{}/'.format(organizer.slug, giftcard.pk),
    )
    assert resp.status_code == 405


@pytest.mark.django_db
def test_giftcard_transactions(token_client, organizer, giftcard):
    resp = token_client.get(
        '/api/v1/organizers/{}/giftcards/{}/transactions/'.format(organizer.slug, giftcard.pk),
    )
    assert resp.status_code == 200
    assert resp.data == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": giftcard.transactions.first().pk,
                "datetime": giftcard.transactions.first().datetime.isoformat().replace("+00:00", "Z"),
                "value": "23.00",
                "event": None,
                "order": None,
                "text": None,
                "info": None,
                "acceptor": organizer.slug
            }
        ]
    }
