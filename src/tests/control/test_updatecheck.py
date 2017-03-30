import pytest

from pretix.base.models import User


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

    r = client.get('/control/global/update/')  # Click it
    r = client.get('/control/')
    assert 'pretix automatically checks for updates in the background' not in r.content.decode()
