import pytest


@pytest.fixture
def token_client(client, team):
    team.can_view_orders = True
    team.can_view_vouchers = True
    team.save()
    t = team.tokens.create(name='Foo')
    client.credentials(HTTP_AUTHORIZATION='Token ' + t.token)
    return client


TEST_ORGANIZER_RES = {
    "name": "Dummy",
    "slug": "dummy"
}


@pytest.mark.django_db
def test_organizer_list(token_client, organizer):
    resp = token_client.get('/api/v1/organizers/')
    assert resp.status_code == 200
    assert TEST_ORGANIZER_RES in resp.data['results']


@pytest.mark.django_db
def test_organizer_detail(token_client, organizer):
    resp = token_client.get('/api/v1/organizers/{}/'.format(organizer.slug))
    assert resp.status_code == 200
    assert TEST_ORGANIZER_RES == resp.data
