import datetime
from unittest import mock

import pytest
from pytz import UTC

from pretix.base.models import WaitingListEntry


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def wle(event, item):
    testtime = datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        return WaitingListEntry.objects.create(event=event, item=item, email="waiting@example.org", locale="en")


TEST_WLE_RES = {
    "id": 1,
    "created": "2017-12-01T10:00:00Z",
    "email": "waiting@example.org",
    "voucher": None,
    "item": 2,
    "variation": None,
    "locale": "en",
    "subevent": None,
}


@pytest.mark.django_db
def test_wle_list(token_client, organizer, event, wle, item, subevent):
    var = item.variations.create(value="Children")
    res = dict(TEST_WLE_RES)
    wle.variation = var
    wle.save()
    res["id"] = wle.pk
    res["item"] = item.pk
    res["variation"] = var.pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/waitinglistentries/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?item={}'.format(organizer.slug, event.slug, item.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?item={}'.format(organizer.slug, event.slug, item.pk + 1))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?variation={}'.format(organizer.slug, event.slug, var.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?variation={}'.format(organizer.slug, event.slug, var.pk + 1))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?email=waiting@example.org'.format(
            organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?email=foo@bar.sample'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?locale=en'.format(
            organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?locale=de'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?has_voucher=false'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?has_voucher=true'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']

    v = event.vouchers.create(item=item, price_mode='set', value=12, tag='Foo')
    wle.voucher = v
    wle.save()
    res['voucher'] = v.pk
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?has_voucher=true'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']

    wle.subevent = subevent
    wle.save()
    res['subevent'] = subevent.pk

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?subevent={}'.format(organizer.slug, event.slug, subevent.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?subevent={}'.format(organizer.slug, event.slug,
                                                                                 subevent.pk + 1))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_wle_detail(token_client, organizer, event, wle, item):
    res = dict(TEST_WLE_RES)
    res["id"] = wle.pk
    res["item"] = item.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/waitinglistentries/{}/'.format(organizer.slug, event.slug,
                                                                                            wle.pk))
    assert resp.status_code == 200
    assert res == resp.data
