import copy

import pytest
from django_scopes import scopes_disabled

from pretix.api.models import WebHook


@pytest.fixture
def webhook(organizer, event):
    wh = organizer.webhooks.create(
        enabled=True,
        target_url='https://google.com',
        all_events=False
    )
    wh.limit_events.add(event)
    wh.listeners.create(action_type='pretix.event.order.placed')
    wh.listeners.create(action_type='pretix.event.order.paid')
    return wh


TEST_WEBHOOK_RES = {
    "id": 1,
    "enabled": True,
    "target_url": "https://google.com",
    "all_events": False,
    "limit_events": ['dummy'],
    "action_types": ['pretix.event.order.paid', 'pretix.event.order.placed'],
}


@pytest.mark.django_db
def test_hook_list(token_client, organizer, event, webhook):
    res = dict(TEST_WEBHOOK_RES)
    res["id"] = webhook.pk

    resp = token_client.get('/api/v1/organizers/{}/webhooks/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_hook_detail(token_client, organizer, event, webhook):
    res = dict(TEST_WEBHOOK_RES)
    res["id"] = webhook.pk
    resp = token_client.get('/api/v1/organizers/{}/webhooks/{}/'.format(organizer.slug, webhook.pk))
    assert resp.status_code == 200
    assert res == resp.data


TEST_WEBHOOK_CREATE_PAYLOAD = {
    "enabled": True,
    "target_url": "https://google.com",
    "all_events": False,
    "limit_events": ['dummy'],
    "action_types": ['pretix.event.order.placed', 'pretix.event.order.paid'],
}


@pytest.mark.django_db
def test_hook_create(token_client, organizer, event):
    resp = token_client.post(
        '/api/v1/organizers/{}/webhooks/'.format(organizer.slug),
        TEST_WEBHOOK_CREATE_PAYLOAD,
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        cl = WebHook.objects.get(pk=resp.data['id'])
        assert cl.target_url == "https://google.com"
        assert cl.limit_events.count() == 1
        assert set(cl.listeners.values_list('action_type', flat=True)) == {'pretix.event.order.placed',
                                                                           'pretix.event.order.paid'}
        assert not cl.all_events


@pytest.mark.django_db
def test_hook_create_either_all_or_limit(token_client, organizer, event):
    res = copy.copy(TEST_WEBHOOK_CREATE_PAYLOAD)
    res['all_events'] = True
    resp = token_client.post(
        '/api/v1/organizers/{}/webhooks/'.format(organizer.slug),
        res,
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {'non_field_errors': ['You can set either limit_events or all_events.']}


@pytest.mark.django_db
def test_hook_create_invalid_url(token_client, organizer, event):
    res = copy.copy(TEST_WEBHOOK_CREATE_PAYLOAD)
    res['target_url'] = 'foo.bar'
    resp = token_client.post(
        '/api/v1/organizers/{}/webhooks/'.format(organizer.slug),
        res,
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {'target_url': ['Enter a valid URL.']}


@pytest.mark.django_db
def test_hook_create_invalid_event(token_client, organizer, event):
    res = copy.copy(TEST_WEBHOOK_CREATE_PAYLOAD)
    res['limit_events'] = ['foo']
    resp = token_client.post(
        '/api/v1/organizers/{}/webhooks/'.format(organizer.slug),
        res,
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {'limit_events': ['Object with slug=foo does not exist.']}


@pytest.mark.django_db
def test_hook_create_invalid_action_types(token_client, organizer, event):
    res = copy.copy(TEST_WEBHOOK_CREATE_PAYLOAD)
    res['action_types'] = ['foo']
    resp = token_client.post(
        '/api/v1/organizers/{}/webhooks/'.format(organizer.slug),
        res,
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {'action_types': ['Invalid action type "foo".']}


@pytest.mark.django_db
def test_hook_patch_url(token_client, organizer, event, webhook):
    resp = token_client.patch(
        '/api/v1/organizers/{}/webhooks/{}/'.format(organizer.slug, webhook.pk),
        {
            'target_url': 'https://pretix.eu'
        },
        format='json'
    )
    assert resp.status_code == 200
    webhook.refresh_from_db()
    assert webhook.target_url == "https://pretix.eu"
    with scopes_disabled():
        assert webhook.limit_events.count() == 1
        assert set(webhook.listeners.values_list('action_type', flat=True)) == {'pretix.event.order.placed',
                                                                                'pretix.event.order.paid'}
    assert webhook.enabled


@pytest.mark.django_db
def test_hook_patch_types(token_client, organizer, event, webhook):
    resp = token_client.patch(
        '/api/v1/organizers/{}/webhooks/{}/'.format(organizer.slug, webhook.pk),
        {
            'action_types': ['pretix.event.order.placed', 'pretix.event.order.canceled']
        },
        format='json'
    )
    assert resp.status_code == 200
    webhook.refresh_from_db()
    with scopes_disabled():
        assert webhook.limit_events.count() == 1
        assert set(webhook.listeners.values_list('action_type', flat=True)) == {'pretix.event.order.placed',
                                                                                'pretix.event.order.canceled'}
    assert webhook.enabled


@pytest.mark.django_db
def test_hook_delete(token_client, organizer, event, webhook):
    resp = token_client.delete(
        '/api/v1/organizers/{}/webhooks/{}/'.format(organizer.slug, webhook.pk),
    )
    assert resp.status_code == 204
    webhook.refresh_from_db()
    assert not webhook.enabled
