import pytest

TEST_SUBEVENT_RES = {
    'active': False,
    'presale_start': None,
    'date_to': None,
    'date_admission': None,
    'name': {'en': 'Foobar'},
    'date_from': '2017-12-27T10:00:00Z',
    'presale_end': None,
    'id': 1,
    'variation_price_overrides': [],
    'location': None,
    'item_price_overrides': [],
    'meta_data': {'type': 'Workshop'}
}


@pytest.mark.django_db
def test_subevent_list(token_client, organizer, event, subevent):
    res = dict(TEST_SUBEVENT_RES)
    res["id"] = subevent.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/subevents/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    print(dict(resp.data['results'][0]))
    assert [res] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/subevents/?active=false'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/subevents/?active=true'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_subevent_detail(token_client, organizer, event, subevent):
    res = dict(TEST_SUBEVENT_RES)
    res["id"] = subevent.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/subevents/{}/'.format(organizer.slug, event.slug,
                                                                                   subevent.pk))
    assert resp.status_code == 200
    assert res == resp.data
