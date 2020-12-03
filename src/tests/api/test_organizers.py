import pytest

from pretix.testutils.mock import mocker_context

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
    with mocker_context() as mocker:
        mocked = mocker.patch('pretix.presale.style.regenerate_organizer_css.apply_async')

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
        mocked.assert_not_called()

        resp = token_client.put(
            '/api/v1/organizers/{}/settings/'.format(organizer.slug),
            {
                'event_list_type': 'put-not-allowed'
            },
            format='json'
        )
        assert resp.status_code == 405

        resp = token_client.patch(
            '/api/v1/organizers/{}/settings/'.format(organizer.slug),
            {
                'primary_color': 'invalid-color'
            },
            format='json'
        )
        assert resp.status_code == 400

        resp = token_client.patch(
            '/api/v1/organizers/{}/settings/'.format(organizer.slug),
            {
                'primary_color': '#ff0000'
            },
            format='json'
        )
        assert resp.status_code == 200
        mocked.assert_any_call(args=(organizer.pk,))
