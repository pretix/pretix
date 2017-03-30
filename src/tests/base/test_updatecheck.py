import json

import pytest
import responses

from django.core import mail as djmail

from pretix.base.services import update_check
from pretix.base.settings import GlobalSettingsObject


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


def request_callback_not_updatable(request):
    json_data = json.loads(request.body.decode())
    resp_body = {
        'status': 'ok',
        'version': {
            'latest': '1.0.0',
            'yours': json_data.get('version'),
            'updatable': False
        },
        'plugins': {}
    }
    return 200, {'Content-Type': 'text/json'}, json.dumps(resp_body)


def request_callback_disallowed(request):
    pytest.fail("Request issued even though none should be issued.")


@pytest.mark.django_db
@responses.activate
def test_update_check_disabled():
    gs = GlobalSettingsObject()
    gs.settings.update_check_perform = False

    responses.add_callback(
        responses.POST, 'https://pretix.eu/.update_check/',
        callback=request_callback_disallowed,
        content_type='application/json',
    )
    update_check.update_check.apply(throw=True)


@pytest.mark.django_db
@responses.activate
def test_update_check_sent_no_updates():
    responses.add_callback(
        responses.POST, 'https://pretix.eu/.update_check/',
        callback=request_callback_not_updatable,
        content_type='application/json',
    )
    update_check.update_check.apply(throw=True)
    gs = GlobalSettingsObject()
    assert not gs.settings.update_check_result_warning
    storeddata = gs.settings.update_check_result
    assert not storeddata['version']['updatable']


@pytest.mark.django_db
@responses.activate
def test_update_check_sent_updates():
    responses.add_callback(
        responses.POST, 'https://pretix.eu/.update_check/',
        callback=request_callback_updatable,
        content_type='application/json',
    )
    update_check.update_check.apply(throw=True)
    gs = GlobalSettingsObject()
    assert gs.settings.update_check_result_warning
    storeddata = gs.settings.update_check_result
    assert storeddata['version']['updatable']


@pytest.mark.django_db
@responses.activate
def test_update_check_mail_sent():
    gs = GlobalSettingsObject()
    gs.settings.update_check_email = 'test@example.org'

    responses.add_callback(
        responses.POST, 'https://pretix.eu/.update_check/',
        callback=request_callback_updatable,
        content_type='application/json',
    )
    update_check.update_check.apply(throw=True)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ['test@example.org']
    assert 'update' in djmail.outbox[0].subject


@pytest.mark.django_db
@responses.activate
def test_update_check_mail_sent_only_after_change():
    gs = GlobalSettingsObject()
    gs.settings.update_check_email = 'test@example.org'

    with responses.RequestsMock() as rsps:
        rsps.add_callback(
            responses.POST, 'https://pretix.eu/.update_check/',
            callback=request_callback_updatable,
            content_type='application/json',
        )

        update_check.update_check.apply(throw=True)
        assert len(djmail.outbox) == 1

        update_check.update_check.apply(throw=True)
        assert len(djmail.outbox) == 1

    with responses.RequestsMock() as rsps:
        rsps.add_callback(
            responses.POST, 'https://pretix.eu/.update_check/',
            callback=request_callback_not_updatable,
            content_type='application/json',
        )

        update_check.update_check.apply(throw=True)
        assert len(djmail.outbox) == 1

    with responses.RequestsMock() as rsps:
        rsps.add_callback(
            responses.POST, 'https://pretix.eu/.update_check/',
            callback=request_callback_updatable,
            content_type='application/json',
        )

        update_check.update_check.apply(throw=True)
        assert len(djmail.outbox) == 2
