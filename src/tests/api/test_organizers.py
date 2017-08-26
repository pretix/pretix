import pytest

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
