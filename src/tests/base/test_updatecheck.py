import json
from datetime import timedelta

import pytest
import responses
from django.core import mail as djmail
from django.utils.timezone import now

from pretix import __version__
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


@pytest.mark.django_db
def test_update_cron_interval(monkeypatch):
    called = False

    def callee():
        nonlocal called
        called = True

    monkeypatch.setattr(update_check.update_check, 'apply_async', callee)

    gs = GlobalSettingsObject()
    gs.settings.update_check_email = 'test@example.org'

    gs.settings.update_check_last = now() - timedelta(hours=14)
    update_check.run_update_check(None)
    assert not called

    gs.settings.update_check_last = now() - timedelta(hours=24)
    update_check.run_update_check(None)
    assert called


@pytest.mark.django_db
def test_result_table_empty():
    assert update_check.check_result_table() == {
        'error': 'no_result'
    }


@responses.activate
@pytest.mark.django_db
def test_result_table_up2date():
    responses.add_callback(
        responses.POST, 'https://pretix.eu/.update_check/',
        callback=request_callback_not_updatable,
        content_type='application/json',
    )
    update_check.update_check.apply(throw=True)
    tbl = update_check.check_result_table()
    assert tbl[0] == ('pretix', __version__, '1.0.0', False)
    assert tbl[1][0].startswith('Plugin: ')
    assert tbl[1][2] == '?'
