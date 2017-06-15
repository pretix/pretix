import pytest


@pytest.fixture
def token_client(client, team):
    team.can_view_orders = True
    team.can_view_vouchers = True
    team.save()
    t = team.tokens.create(name='Foo')
    client.credentials(HTTP_AUTHORIZATION='Token ' + t.token)
    return client


TEST_EVENT_RES = {
    "name": {"en": "Dummy"},
    "live": False,
    "currency": "EUR",
    "date_from": "2017-12-27T10:00:00Z",
    "date_to": None,
    "date_admission": None,
    "is_public": False,
    "presale_start": None,
    "presale_end": None,
    "location": None,
    "slug": "dummy",
}


@pytest.mark.django_db
def test_event_list(token_client, organizer, event):
    resp = token_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert resp.status_code == 200
    print(resp.data)
    assert TEST_EVENT_RES == dict(resp.data['results'][0])


@pytest.mark.django_db
def test_event_detail(token_client, organizer, event, team):
    team.all_events = True
    team.save()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert TEST_EVENT_RES == resp.data
