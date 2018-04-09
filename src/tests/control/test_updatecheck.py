import json

import pytest
import responses

from pretix.base.models import User
from pretix.base.settings import GlobalSettingsObject


@pytest.fixture
def user():
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    return user


def request_callback_updatable(request):
    json_data = json.loads(request.body.decode())
    resp_body = {
        'status': 'ok',
        'version': {
            'latest': '1000.0.0',
            'yours': json_data.get('version'),
            'updatable': True
        },
        'plugins': {}
    }
    return 200, {'Content-Type': 'text/json'}, json.dumps(resp_body)


@pytest.mark.django_db
def test_update_notice_displayed(client, user):
    client.login(email='dummy@dummy.dummy', password='dummy')

    r = client.get('/control/')
    assert 'pretix automatically checks for updates in the background' not in r.content.decode()

    user.is_staff = True
    user.save()
    r = client.get('/control/')
    assert 'pretix automatically checks for updates in the background' in r.content.decode()

    client.get('/control/global/update/')  # Click it
    r = client.get('/control/')
    assert 'pretix automatically checks for updates in the background' not in r.content.decode()


@pytest.mark.django_db
def test_settings(client, user):
    user.is_staff = True
    user.save()
    client.login(email='dummy@dummy.dummy', password='dummy')

    client.post('/control/global/update/', {'update_check_email': 'test@example.org', 'update_check_perform': 'on'})
    gs = GlobalSettingsObject()
    gs.settings.flush()
    assert gs.settings.update_check_perform
    assert gs.settings.update_check_email

    client.post('/control/global/update/', {'update_check_email': '', 'update_check_perform': ''})
    gs.settings.flush()
    assert not gs.settings.update_check_perform
    assert not gs.settings.update_check_email


@pytest.mark.django_db
@responses.activate
def test_trigger(client, user):
    responses.add_callback(
        responses.POST, 'https://pretix.eu/.update_check/',
        callback=request_callback_updatable,
        content_type='application/json',
    )

    user.is_staff = True
    user.save()
    client.login(email='dummy@dummy.dummy', password='dummy')

    gs = GlobalSettingsObject()
    assert not gs.settings.update_check_last
    client.post('/control/global/update/', {'trigger': 'on'})
    gs.settings.flush()
    assert gs.settings.update_check_last
