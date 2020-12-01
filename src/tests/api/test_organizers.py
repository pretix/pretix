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


@pytest.mark.django_db
def test_get_settings(token_client, organizer):
    organizer.settings.event_list_type = "week"
    resp = token_client.get(
        '/api/v1/organizers/{}/settings/'.format(organizer.slug,),
    )
    assert resp.status_code == 200
    assert resp.data['event_list_type'] == "week"

    resp = token_client.get(
        '/api/v1/organizers/{}/settings/?explain=true'.format(organizer.slug),
    )
    assert resp.status_code == 200
    assert resp.data['event_list_type'] == {
        "value": "week",
        "label": "Default overview style",
        "help_text": "If your event series has more than 50 dates in the future, only the month or week calendar can be used."
    }


@pytest.mark.django_db
def test_patch_settings(token_client, organizer):
    organizer.settings.event_list_type = 'week'
    resp = token_client.patch(
        '/api/v1/organizers/{}/settings/'.format(organizer.slug),
        {
            'event_list_type': 'list'
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data['event_list_type'] == "list"
    organizer.settings.flush()
    assert organizer.settings.event_list_type == 'list'

    resp = token_client.patch(
        '/api/v1/organizers/{}/settings/'.format(organizer.slug),
        {
            'event_list_type': None,
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data['event_list_type'] == "list"
    organizer.settings.flush()
    assert organizer.settings.event_list_type == 'list'

    resp = token_client.put(
        '/api/v1/organizers/{}/settings/'.format(organizer.slug),
        {
            'event_list_type': 'invalid'
        },
        format='json'
    )
    assert resp.status_code == 405
