import copy
from decimal import Decimal

import pytest
from django_scopes import scopes_disabled

from pretix.base.models import GiftCard


@pytest.fixture
def giftcard(organizer, event):
    gc = organizer.issued_gift_cards.create(secret="ABCDEF", currency="EUR")
    gc.transactions.create(value=Decimal('23.00'))
    return gc


TEST_GC_RES = {
    "id": 1,
    "secret": "ABCDEF",
    "value": "23.00",
    "currency": "EUR"
}


@pytest.mark.django_db
def test_giftcard_list(token_client, organizer, event, giftcard):
    res = dict(TEST_GC_RES)
    res["id"] = giftcard.pk
    res["issuance"] = giftcard.issuance.isoformat().replace('+00:00', 'Z')

    resp = token_client.get('/api/v1/organizers/{}/giftcards/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_giftcard_detail(token_client, organizer, event, giftcard):
    res = dict(TEST_GC_RES)
    res["id"] = giftcard.pk
    res["issuance"] = giftcard.issuance.isoformat().replace('+00:00', 'Z')
    resp = token_client.get('/api/v1/organizers/{}/giftcards/{}/'.format(organizer.slug, giftcard.pk))
    assert resp.status_code == 200
    assert res == resp.data


TEST_GIFTCARD_CREATE_PAYLOAD = {
    "secret": "DEFABC",
    "value": "12.00",
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
def test_giftcard_patch(token_client, organizer, event, giftcard):
    resp = token_client.patch(
        '/api/v1/organizers/{}/giftcards/{}/'.format(organizer.slug, giftcard.pk),
        {
            'secret': 'foo',
            'value': '10.00',
            'currency': 'USD'
        },
        format='json'
    )
    assert resp.status_code == 200
    giftcard.refresh_from_db()
    assert giftcard.value == Decimal('10.00')
    assert giftcard.secret == "ABCDEF"
    assert giftcard.currency == "EUR"


@pytest.mark.django_db
def test_giftcard_no_deletion(token_client, organizer, event, giftcard):
    resp = token_client.delete(
        '/api/v1/organizers/{}/giftcards/{}/'.format(organizer.slug, giftcard.pk),
    )
    assert resp.status_code == 405
