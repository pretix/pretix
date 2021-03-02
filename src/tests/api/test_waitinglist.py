import copy
import datetime
from unittest import mock

import pytest
from django_scopes import scopes_disabled
from pytz import UTC

from pretix.base.models import WaitingListEntry


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def quota(event, item):
    q = event.quotas.create(name="Budget Ticket", size=0)
    q.items.add(item)
    return q


@pytest.fixture
def wle(event, item):
    testtime = datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        return WaitingListEntry.objects.create(event=event, item=item, email="waiting@example.org", locale="en")


TEST_WLE_RES = {
    "id": 1,
    "created": "2017-12-01T10:00:00Z",
    "name": None,
    "name_parts": {},
    "email": "waiting@example.org",
    "phone": None,
    "voucher": None,
    "item": 2,
    "variation": None,
    "locale": "en",
    "priority": 0,
    "subevent": None,
}


@pytest.mark.django_db
def test_wle_list(token_client, organizer, event, wle, item, subevent):
    with scopes_disabled():
        var = item.variations.create(value="Children")
        var2 = item.variations.create(value="Children")
    res = dict(TEST_WLE_RES)
    wle.variation = var
    wle.save()
    i2 = copy.copy(item)
    i2.pk = None
    i2.save()
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
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?item={}'.format(organizer.slug, event.slug, i2.pk))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?variation={}'.format(organizer.slug, event.slug, var.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?variation={}'.format(organizer.slug, event.slug, var2.pk))
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

    with scopes_disabled():
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
    with scopes_disabled():
        se2 = event.subevents.create(name="Foobar", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC))
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/?subevent={}'.format(organizer.slug, event.slug,
                                                                                 se2.pk))
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


@pytest.mark.django_db
def test_delete_wle(token_client, organizer, event, wle, item):
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/{}/'.format(organizer.slug, event.slug, wle.pk),
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert not event.waitinglistentries.filter(pk=wle.id).exists()


@pytest.mark.django_db
def test_delete_wle_assigned(token_client, organizer, event, wle, item):
    with scopes_disabled():
        v = event.vouchers.create(item=item, price_mode='set', value=12, tag='Foo')
    wle.voucher = v
    wle.save()
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/{}/'.format(organizer.slug, event.slug, wle.pk),
    )
    assert resp.status_code == 403
    with scopes_disabled():
        assert event.waitinglistentries.filter(pk=wle.id).exists()


def create_wle(token_client, organizer, event, data, expected_failure=False):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/'.format(organizer.slug, event.slug),
        data=data, format='json'
    )
    if expected_failure:
        assert resp.status_code == 400
    else:
        assert resp.status_code == 201
        with scopes_disabled():
            return WaitingListEntry.objects.get(pk=resp.data['id'])


@pytest.mark.django_db
def test_wle_create_success(token_client, organizer, event, item, quota):
    w = create_wle(
        token_client, organizer, event,
        data={
            'email': 'testdummy@pretix.eu',
            'item': item.pk,
            'variation': None,
            'locale': 'en',
            'subevent': None
        },
        expected_failure=False
    )
    assert w.email == "testdummy@pretix.eu"
    assert w.item == item
    assert w.variation is None
    assert w.locale == 'en'


@pytest.mark.django_db
def test_wle_require_fields(token_client, organizer, event, item, quota):
    create_wle(
        token_client, organizer, event,
        data={
            'item': item.pk,
            'variation': None,
            'locale': 'en',
            'subevent': None
        },
        expected_failure=True
    )
    create_wle(
        token_client, organizer, event,
        data={
            'email': 'testdummy@pretix.eu',
            'variation': None,
            'locale': 'en',
            'subevent': None
        },
        expected_failure=True
    )
    with scopes_disabled():
        v = item.variations.create(value="S")
    create_wle(
        token_client, organizer, event,
        data={
            'email': 'testdummy@pretix.eu',
            'item': item.pk,
            'variation': None,
            'locale': 'en',
            'subevent': None
        },
        expected_failure=True
    )
    event.has_subevents = True
    create_wle(
        token_client, organizer, event,
        data={
            'email': 'testdummy@pretix.eu',
            'item': item.pk,
            'variation': v.pk,
            'locale': 'en',
            'subevent': None
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_wle_create_available(token_client, organizer, event, item, quota):
    quota.size = 10
    quota.save()
    create_wle(
        token_client, organizer, event,
        data={
            'email': 'testdummy@pretix.eu',
            'item': item.pk,
            'variation': None,
            'locale': 'en',
            'subevent': None
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_wle_create_duplicate(token_client, organizer, event, item, quota):
    create_wle(
        token_client, organizer, event,
        data={
            'email': 'testdummy@pretix.eu',
            'item': item.pk,
            'variation': None,
            'locale': 'en',
            'subevent': None
        },
        expected_failure=False
    )
    create_wle(
        token_client, organizer, event,
        data={
            'email': 'testdummy@pretix.eu',
            'item': item.pk,
            'variation': None,
            'locale': 'en',
            'subevent': None
        },
        expected_failure=True
    )


def change_wle(token_client, organizer, event, wle, data, expected_failure=False):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/{}/'.format(organizer.slug, event.slug, wle.pk),
        data=data, format='json'
    )
    if expected_failure:
        assert resp.status_code in (400, 403)
    else:
        assert resp.status_code == 200
    wle.refresh_from_db()


@pytest.mark.django_db
def test_wle_change_email(token_client, organizer, event, item, wle, quota):
    change_wle(
        token_client, organizer, event, wle,
        data={
            'email': 'foo@pretix.eu',
        },
        expected_failure=False
    )
    assert wle.email == 'foo@pretix.eu'


@pytest.mark.django_db
def test_wle_change_assigned(token_client, organizer, event, item, wle, quota):
    with scopes_disabled():
        v = event.vouchers.create(item=item, price_mode='set', value=12, tag='Foo')
    wle.voucher = v
    wle.save()
    change_wle(
        token_client, organizer, event, wle,
        data={
            'email': 'foo@pretix.eu',
        },
        expected_failure=True
    )
    assert wle.email == 'waiting@example.org'


@pytest.mark.django_db
def test_wle_change_to_available_item(token_client, organizer, event, item, wle, quota):
    with scopes_disabled():
        i = event.items.create(name="Budget Ticket", default_price=23)
        q = event.quotas.create(name="Budget Ticket", size=1)
    q.items.add(i)
    change_wle(
        token_client, organizer, event, wle,
        data={
            'item': i.pk
        },
        expected_failure=True
    )
    assert wle.item == item


@pytest.mark.django_db
def test_wle_change_to_unavailable_item(token_client, organizer, event, item, wle, quota):
    with scopes_disabled():
        i = event.items.create(name="Budget Ticket", default_price=23)
        v = i.variations.create(value="S")
        q = event.quotas.create(name="Budget Ticket", size=0)
    q.items.add(i)
    q.variations.add(v)
    change_wle(
        token_client, organizer, event, wle,
        data={
            'item': i.pk,
            'variation': v.pk
        },
        expected_failure=False
    )
    assert wle.item == i
    assert wle.variation == v


@pytest.mark.django_db
def test_wle_change_to_unavailable_item_missing_var(token_client, organizer, event, item, wle, quota):
    with scopes_disabled():
        i = event.items.create(name="Budget Ticket", default_price=23)
        v = i.variations.create(value="S")
        q = event.quotas.create(name="Budget Ticket", size=0)
    q.items.add(i)
    q.variations.add(v)
    change_wle(
        token_client, organizer, event, wle,
        data={
            'item': i.pk,
        },
        expected_failure=True
    )
    assert wle.item == item
    assert wle.variation is None


@pytest.mark.django_db
def test_wle_change_subevent_of_wrong_event(token_client, organizer, event, item, wle, subevent, subevent2):
    wle.subevent = subevent
    wle.save()
    change_wle(
        token_client, organizer, event, wle,
        data={
            'subevent': subevent2.pk,
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_wle_change_to_duplicate(token_client, organizer, event, item, wle, quota):
    wle.pk = None
    wle.email = 'foo@pretix.eu'
    wle.save()
    change_wle(
        token_client, organizer, event, wle,
        data={
            'email': 'waiting@example.org',
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_wle_send_voucher(token_client, organizer, event, item, wle, quota):
    quota.size = 10
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/{}/send_voucher/'.format(organizer.slug, event.slug,
                                                                                     wle.pk),
        data={}, format='json'
    )
    assert resp.status_code == 204
    wle.refresh_from_db()
    assert wle.voucher


@pytest.mark.django_db
def test_wle_send_voucher_twice(token_client, organizer, event, item, wle, quota):
    quota.size = 10
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/{}/send_voucher/'.format(organizer.slug, event.slug,
                                                                                     wle.pk),
        data={}, format='json'
    )
    assert resp.status_code == 204
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/{}/send_voucher/'.format(organizer.slug, event.slug,
                                                                                     wle.pk),
        data={}, format='json'
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_wle_send_voucher_unavailable(token_client, organizer, event, item, wle, quota):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/waitinglistentries/{}/send_voucher/'.format(organizer.slug, event.slug,
                                                                                     wle.pk),
        data={}, format='json'
    )
    assert resp.status_code == 400
    wle.refresh_from_db()
    assert not wle.voucher
