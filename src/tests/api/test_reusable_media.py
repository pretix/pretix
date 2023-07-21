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
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, GiftCardAcceptance, Order, Organizer, ReusableMedium,
)


@pytest.fixture
def giftcard(organizer):
    gc = organizer.issued_gift_cards.create(secret="ABCDEF", currency="EUR")
    gc.transactions.create(value=Decimal('23.00'), acceptor=organizer)
    return gc


@pytest.fixture
def medium(organizer):
    m = organizer.reusable_media.create(identifier="ABCDEFGH", type="barcode", active=True)
    return m


@pytest.fixture
def organizer2():
    return Organizer.objects.create(name='Partner', slug='partner')


@pytest.fixture
def giftcard2(organizer2):
    gc = organizer2.issued_gift_cards.create(secret="IJKLMNOP", currency="EUR")
    gc.transactions.create(value=Decimal('23.00'), acceptor=organizer2)
    return gc


@pytest.fixture
def medium2(organizer2):
    m = organizer2.reusable_media.create(identifier="ABCDEFGH", type="barcode", active=True)
    return m


@pytest.fixture
@scopes_disabled()
def org2_event(organizer2):
    e = Event.objects.create(
        organizer=organizer2, name='Dummy2', slug='dummy2',
        date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=timezone.utc),
        plugins='pretix.plugins.banktransfer,pretix.plugins.ticketoutputpdf'
    )
    return e


@pytest.fixture
def customer(organizer, event):
    return organizer.customers.create(
        identifier="8WSAJCJ",
        email="foo@example.org",
        name_parts={"_legacy": "Foo"},
        name_cached="Foo",
        is_verified=False,
    )


TEST_MEDIUM_RES = {
    "id": 1,
    "organizer": "dummy",
    "identifier": "ABCDEFGH",
    "type": "barcode",
    "active": True,
    "expires": None,
    "customer": None,
    "linked_orderposition": None,
    "linked_giftcard": None,
    "notes": None,
    "info": {},
}


@pytest.mark.django_db
def test_medium_list(token_client, organizer, event, medium):
    res = dict(TEST_MEDIUM_RES)
    res["id"] = medium.pk
    res["created"] = medium.created.isoformat().replace('+00:00', 'Z')
    res["updated"] = medium.updated.isoformat().replace('+00:00', 'Z')

    resp = token_client.get('/api/v1/organizers/{}/reusablemedia/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/reusablemedia/?identifier=XYZABC'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/reusablemedia/?identifier=ABCDEFGH'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_medium_detail(token_client, organizer, event, medium, giftcard, customer):
    res = dict(TEST_MEDIUM_RES)
    res["id"] = medium.pk
    res["created"] = medium.created.isoformat().replace('+00:00', 'Z')
    res["updated"] = medium.updated.isoformat().replace('+00:00', 'Z')
    resp = token_client.get('/api/v1/organizers/{}/reusablemedia/{}/'.format(organizer.slug, medium.pk))
    assert resp.status_code == 200
    assert res == resp.data

    with scopes_disabled():
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, datetime=now(), expires=now() + timedelta(days=10),
            total=14, locale='en'
        )
        ticket = event.items.create(name='Early-bird ticket', category=None, default_price=23, admission=True,
                                    personalized=True)
        op = o.positions.create(item=ticket, price=Decimal("14"))
        medium.linked_orderposition = op
        medium.linked_giftcard = giftcard
        medium.customer = customer
        medium.save()
        giftcard.owner_ticket = op
        giftcard.save()
        resp = token_client.get(
            '/api/v1/organizers/{}/reusablemedia/{}/?expand=linked_giftcard&expand='
            'linked_giftcard.owner_ticket&expand=linked_orderposition&expand=customer'.format(
                organizer.slug, medium.pk
            )
        )
        assert resp.status_code == 200

        assert resp.data["customer"] == {
            "identifier": customer.identifier,
            "external_identifier": None,
            "email": "foo@example.org",
            "name": "Foo",
            "name_parts": {"_legacy": "Foo"},
            "is_active": True,
            "is_verified": False,
            "last_login": None,
            "date_joined": customer.date_joined.isoformat().replace("+00:00", "Z"),
            "locale": "en",
            "last_modified": customer.last_modified.isoformat().replace("+00:00", "Z"),
            "notes": None
        }
        assert resp.data["linked_orderposition"] == {
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
        assert resp.data["linked_giftcard"] == {
            "id": giftcard.pk,
            "secret": "ABCDEF",
            "issuance": giftcard.issuance.isoformat().replace("+00:00", "Z"),
            "value": "23.00",
            "currency": "EUR",
            "testmode": False,
            "expires": None,
            "conditions": None,
            "owner_ticket": resp.data["linked_orderposition"],
            "issuer": "dummy",
        }


TEST_MEDIUM_CREATE_PAYLOAD = {
    "type": "barcode",
    "identifier": "FOOBAR",
    "active": True,
    "info": {"foo": "bar"}
}


@pytest.mark.django_db
def test_medium_create(token_client, organizer, giftcard):
    payload = dict(TEST_MEDIUM_CREATE_PAYLOAD)
    payload['linked_giftcard'] = giftcard.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/reusablemedia/'.format(organizer.slug),
        payload,
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        m = ReusableMedium.objects.get(pk=resp.data['id'])
        assert m.organizer == organizer
        assert m.type == "barcode"
        assert m.identifier == "FOOBAR"
        assert m.active
        assert m.linked_giftcard == giftcard
        assert m.info == {"foo": "bar"}
        assert m.created > now() - timedelta(minutes=10)
        assert m.updated > now() - timedelta(minutes=10)


@pytest.mark.django_db
def test_medium_foreignkeyval(token_client, organizer, giftcard2):
    payload = dict(TEST_MEDIUM_CREATE_PAYLOAD)
    payload['linked_giftcard'] = giftcard2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/reusablemedia/'.format(organizer.slug),
        payload,
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {'linked_giftcard': [f'Invalid pk "{giftcard2.pk}" - object does not exist.']}


@pytest.mark.django_db
def test_medium_create_duplicate(token_client, organizer, event, medium):
    payload = dict(TEST_MEDIUM_CREATE_PAYLOAD)
    payload['identifier'] = medium.identifier
    resp = token_client.post(
        '/api/v1/organizers/{}/reusablemedia/'.format(organizer.slug),
        payload,
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {
        'identifier': ['A medium with the same identifier and type already exists in your organizer account.']}


@pytest.mark.django_db
def test_medium_patch(token_client, organizer, event, medium, giftcard, customer):
    resp = token_client.patch(
        '/api/v1/organizers/{}/reusablemedia/{}/'.format(organizer.slug, medium.pk),
        {
            'linked_giftcard': giftcard.pk,
            'customer': customer.identifier,
            'info': {'test': 2},
            'identifier': 'WILLBEIGNORED',
        },
        format='json'
    )
    assert resp.status_code == 200
    medium.refresh_from_db()
    assert medium.linked_giftcard == giftcard
    assert medium.customer == customer
    assert medium.info == {'test': 2}
    assert medium.identifier == "ABCDEFGH"


@pytest.mark.django_db
def test_medium_no_deletion(token_client, organizer, event, medium):
    resp = token_client.delete(
        '/api/v1/organizers/{}/reusablemedia/{}/'.format(organizer.slug, medium.pk),
    )
    assert resp.status_code == 405


@pytest.mark.django_db
def test_medium_lookup_ok(token_client, organizer, event, medium):
    res = dict(TEST_MEDIUM_RES)
    res["id"] = medium.pk
    res["created"] = medium.created.isoformat().replace('+00:00', 'Z')
    res["updated"] = medium.updated.isoformat().replace('+00:00', 'Z')
    resp = token_client.post(
        '/api/v1/organizers/{}/reusablemedia/lookup/'.format(organizer.slug),
        {
            "type": medium.type,
            "identifier": medium.identifier,
        },
        format='json'
    )
    assert resp.status_code == 200
    assert res == resp.data["result"]


@pytest.mark.django_db
def test_medium_lookup_not_found(token_client, organizer, organizer2, medium):
    medium.organizer = organizer2
    medium.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/reusablemedia/lookup/'.format(organizer.slug),
        {
            "type": medium.type,
            "identifier": medium.identifier,
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data["result"] is None


@pytest.mark.django_db
def test_medium_lookup_autocreate(token_client, organizer):
    # Disabled
    resp = token_client.post(
        '/api/v1/organizers/{}/reusablemedia/lookup/'.format(organizer.slug),
        {
            "type": "nfc_uid",
            "identifier": "AABBCCDD",
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data["result"] is None

    # Enabled
    organizer.settings.reusable_media_type_nfc_uid_autocreate_giftcard = True
    organizer.settings.reusable_media_type_nfc_uid_autocreate_giftcard_currency = 'EUR'
    resp = token_client.post(
        '/api/v1/organizers/{}/reusablemedia/lookup/?expand=linked_giftcard'.format(organizer.slug),
        {
            "type": "nfc_uid",
            "identifier": "AABBCCDD",
        },
        format='json'
    )
    assert resp.status_code == 200
    res = resp.data["result"]
    with scopes_disabled():
        m = ReusableMedium.objects.get(pk=res["id"])
    assert res["identifier"] == "AABBCCDD" == m.identifier
    assert res["type"] == "nfc_uid" == m.type
    assert res["linked_giftcard"]["value"] == "0.00"

    # Ignore NFC random UID
    resp = token_client.post(
        '/api/v1/organizers/{}/reusablemedia/lookup/?expand=linked_giftcard'.format(organizer.slug),
        {
            "type": "nfc_uid",
            "identifier": "08080808",
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data["result"] is None


@pytest.mark.django_db
def test_medium_autocreate_giftcard(token_client, organizer):
    organizer.settings.reusable_media_type_nfc_mf0aes_autocreate_giftcard = True
    organizer.settings.reusable_media_type_nfc_mf0aes_autocreate_giftcard_currency = 'USD'
    resp = token_client.post(
        '/api/v1/organizers/{}/reusablemedia/?expand=linked_giftcard'.format(organizer.slug),
        {
            "type": "nfc_mf0aes",
            "identifier": "AABBCCDD",
        },
        format='json'
    )
    assert resp.status_code == 201
    res = resp.data
    with scopes_disabled():
        m = ReusableMedium.objects.get(pk=res["id"])
    assert res["identifier"] == "AABBCCDD" == m.identifier
    assert res["type"] == "nfc_mf0aes" == m.type
    assert res["linked_giftcard"]["value"] == "0.00"
    assert res["linked_giftcard"]["currency"] == "USD"


@pytest.mark.django_db
def test_medium_lookup_cross_organizer(token_client, organizer, organizer2, org2_event, medium2, giftcard2):
    with scopes_disabled():
        o = Order.objects.create(
            code='FOO', event=org2_event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, datetime=now(), expires=now() + timedelta(days=10),
            total=14, locale='en'
        )
        ticket = org2_event.items.create(name='Early-bird ticket', category=None, default_price=23, admission=True,
                                         personalized=True)
        op = o.positions.create(item=ticket, price=Decimal("14"))
        medium2.linked_orderposition = op
        medium2.linked_giftcard = giftcard2
        medium2.save()

    resp = token_client.post(
        '/api/v1/organizers/{}/reusablemedia/lookup/'.format(organizer.slug),
        {
            "type": medium2.type,
            "identifier": medium2.identifier,
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data["result"] is None

    gca = GiftCardAcceptance.objects.create(
        issuer=organizer2,
        acceptor=organizer,
        active=True,
        reusable_media=False
    )

    resp = token_client.post(
        '/api/v1/organizers/{}/reusablemedia/lookup/'.format(organizer.slug),
        {
            "type": medium2.type,
            "identifier": medium2.identifier,
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data["result"] is None

    gca.reusable_media = True
    gca.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/reusablemedia/lookup/'.format(organizer.slug),
        {
            "type": medium2.type,
            "identifier": medium2.identifier,
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data["result"] is not None
    assert resp.data["result"]["organizer"] == "partner"
    assert resp.data["result"]["linked_giftcard"] is not None
    assert resp.data["result"]["linked_orderposition"] is None
