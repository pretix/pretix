import copy
import datetime
from decimal import Decimal
from unittest import mock

import pytest
from pytz import UTC

from pretix.base.models.orders import CartPosition


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


TEST_CARTPOSITION_RES = {
    'id': 1,
    'cart_id': 'aaa',
    'item': 1,
    'variation': None,
    'price': '23.00',
    'attendee_name': None,
    'attendee_email': None,
    'voucher': None,
    'addon_to': None,
    'subevent': None,
    'datetime': '2018-06-11T10:00:00Z',
    'expires': '2018-06-11T10:00:00Z',
    'includes_tax': True,
    'answers': []
}


@pytest.mark.django_db
def test_cp_list(token_client, organizer, event, item, taxrule, question):
    testtime = datetime.datetime(2018, 6, 11, 10, 0, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        cr = CartPosition.objects.create(
            event=event, cart_id="aaa", item=item,
            price=23,
            datetime=datetime.datetime(2018, 6, 11, 10, 0, 0, 0),
            expires=datetime.datetime(2018, 6, 11, 10, 0, 0, 0)
        )
    res = dict(TEST_CARTPOSITION_RES)
    res["id"] = cr.pk
    res["item"] = item.pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/cartpositions/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_cp_detail(token_client, organizer, event, item, taxrule, question):
    testtime = datetime.datetime(2018, 6, 11, 10, 0, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        cr = CartPosition.objects.create(
            event=event, cart_id="aaa", item=item,
            price=23,
            datetime=datetime.datetime(2018, 6, 11, 10, 0, 0, 0),
            expires=datetime.datetime(2018, 6, 11, 10, 0, 0, 0)
        )
    res = dict(TEST_CARTPOSITION_RES)
    res["id"] = cr.pk
    res["item"] = item.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/cartpositions/{}/'.format(organizer.slug, event.slug,
                                                                                       cr.pk))
    assert resp.status_code == 200
    assert res == resp.data


CARTPOS_CREATE_PAYLOAD = {
    'cart_id': 'aaa',
    'item': 1,
    'variation': None,
    'price': '23.00',
    'attendee_name': None,
    'attendee_email': None,
    'addon_to': None,
    'subevent': None,
    'expires': '2018-06-11T10:00:00Z',
    'includes_tax': True,
    'answers': []
}


@pytest.mark.django_db
def test_cartpos_create(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(CARTPOS_CREATE_PAYLOAD)
    res['item'] = item.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    cp = CartPosition.objects.get(pk=resp.data['id'])
    assert cp.price == Decimal('23.00')
    assert cp.item == item


@pytest.mark.django_db
def test_cartpos_cart_id_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(CARTPOS_CREATE_PAYLOAD)
    res['item'] = item.pk
    del res['cart_id']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    cp = CartPosition.objects.get(pk=resp.data['id'])
    assert cp.price == Decimal('23.00')
    assert cp.item == item
    assert len(cp.cart_id) > 48

# cart_id optional
# expires optional
# includes_tax optional
# answers
# quota sold out
