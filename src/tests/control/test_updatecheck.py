import pytest

from pretix.base.models import User
from pretix.base.settings import GlobalSettingsObject


@pytest.fixture
def user():
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    return user


@pytest.mark.django_db
def test_update_notice_displayed(client, user):
    client.login(email='dummy@dummy.dummy', password='dummy')

    r = client.get('/control/')
    assert 'pretix automatically checks for updates in the background' not in r.content.decode()

    user.is_superuser = True
    user.save()
    r = client.get('/control/')
    assert 'pretix automatically checks for updates in the background' in r.content.decode()

    client.get('/control/global/update/')  # Click it
    r = client.get('/control/')
    assert 'pretix automatically checks for updates in the background' not in r.content.decode()


@pytest.mark.django_db
def test_settings(client, user):
    user.is_superuser = True
    user.save()
    client.login(email='dummy@dummy.dummy', password='dummy')

    client.post('/control/global/update/', {'update_check_email': 'test@example.org', 'update_check_perform': 'on'})
    gs = GlobalSettingsObject()
    gs.settings._flush()
    assert gs.settings.update_check_perform
    assert gs.settings.update_check_email

    client.post('/control/global/update/', {'update_check_email': '', 'update_check_perform': ''})
    gs.settings._flush()
    assert not gs.settings.update_check_perform
    assert not gs.settings.update_check_email


@pytest.mark.django_db
def test_trigger(client, user):
    user.is_superuser = True
    user.save()
    client.login(email='dummy@dummy.dummy', password='dummy')

    gs = GlobalSettingsObject()
    assert not gs.settings.update_check_last
    client.post('/control/global/update/', {'trigger': 'on'})
    gs.settings._flush()
    assert gs.settings.update_check_last
