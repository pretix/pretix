import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Device, Event, Organizer, Team, User
from pretix.base.models.devices import generate_api_token


@pytest.fixture
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
def event(organizer):
    event = Event.objects.create(
        organizer=organizer, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


@pytest.fixture
def device(organizer):
    return organizer.devices.create(name='Cashdesk')


@pytest.fixture
def admin_user(admin_team):
    u = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    admin_team.members.add(u)
    return u


@pytest.fixture
def admin_team(organizer):
    return Team.objects.create(organizer=organizer, can_change_organizer_settings=True, name='Admin team')


@pytest.mark.django_db
def test_list_of_devices(event, admin_user, client, device):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/devices')
    assert 'Cashdesk' in resp.content.decode()


@pytest.mark.django_db
def test_create_device(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.post('/control/organizer/dummy/device/add', {
        'name': 'Foo',
        'limit_events': str(event.pk),
    }, follow=True)
    print(resp.status_code, resp.content)
    with scopes_disabled():
        d = Device.objects.last()
        assert d.name == 'Foo'
        assert not d.all_events
        assert list(d.limit_events.all()) == [event]
        assert d.initialization_token in resp.content.decode()


@pytest.mark.django_db
def test_update_device(event, admin_user, admin_team, device, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/device/{}/edit'.format(device.pk), {
        'name': 'Cashdesk 2',
        'limit_events': str(event.pk),
    }, follow=True)
    device.refresh_from_db()
    assert device.name == 'Cashdesk 2'
    assert not device.all_events
    with scopes_disabled():
        assert list(device.limit_events.all()) == [event]


@pytest.mark.django_db
def test_revoke_device(event, admin_user, admin_team, device, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        device.api_token = generate_api_token()
    device.initialized = now()
    device.save()

    client.get('/control/organizer/dummy/device/{}/revoke'.format(device.pk))
    client.post('/control/organizer/dummy/device/{}/revoke'.format(device.pk), {}, follow=True)
    device.refresh_from_db()
    assert device.revoked
