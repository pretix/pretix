import pytest


@pytest.mark.django_db
def test_get(token_client, organizer, event, team):
    resp = token_client.get('/api/v1/organizers/{}/teams'.format(organizer.slug), follow=False)
    assert resp.status_code == 301
    assert resp['Location'].endswith('/')


@pytest.mark.django_db
def test_post(token_client, organizer, event, team):
    resp = token_client.post('/api/v1/organizers/{}/teams'.format(organizer.slug), follow=False)
    assert resp.status_code == 404
