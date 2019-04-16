import pytest
from django.core import mail as djmail
from django.utils.timezone import now

from pretix.base.models import Event, Organizer, Team, User


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
def admin_team(organizer):
    return Team.objects.create(organizer=organizer, can_change_teams=True, name='Admin team')


@pytest.fixture
def admin_user(admin_team):
    u = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    admin_team.members.add(u)
    return u


@pytest.mark.django_db
def test_list_of_teams(event, admin_user, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/teams')
    assert 'Admin team' in resp.rendered_content


@pytest.mark.django_db
def test_team_detail_view(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/team/{}/'.format(admin_team.pk))
    assert 'Admin team' in resp.rendered_content
    assert admin_user.email in resp.rendered_content


@pytest.mark.django_db
def test_team_add_user(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    u = User.objects.create_user('dummy2@dummy.dummy', 'dummy')

    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'user': u.email
    }, follow=True)
    assert 'Admin team' in resp.rendered_content
    assert admin_user.email in resp.rendered_content
    assert u.email in resp.rendered_content
    assert u in admin_team.members.all()


@pytest.mark.django_db
def test_team_create_invite(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    djmail.outbox = []

    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'user': 'foo@example.org'
    }, follow=True)
    assert 'Admin team' in resp.rendered_content
    assert admin_user.email in resp.rendered_content
    assert 'foo@example.org' in resp.rendered_content
    assert admin_team.invites.first().email == 'foo@example.org'
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_team_create_token(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    djmail.outbox = []

    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'name': 'Test token'
    }, follow=True)
    assert 'Test token' in resp.rendered_content
    assert admin_team.tokens.first().name == 'Test token'
    assert admin_team.tokens.first().token in resp.rendered_content


@pytest.mark.django_db
def test_team_remove_token(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    tk = admin_team.tokens.create(name='Test token')
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-token': str(tk.pk)
    }, follow=True)
    assert tk.token not in resp.rendered_content
    assert 'Test token' in resp.rendered_content
    tk.refresh_from_db()
    assert not tk.active


@pytest.mark.django_db
def test_team_resend_invite(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    djmail.outbox = []

    inv = admin_team.invites.create(email='foo@example.org')
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'resend-invite': str(inv.pk)
    }, follow=True)
    assert 'Admin team' in resp.rendered_content
    assert admin_user.email in resp.rendered_content
    assert 'foo@example.org' in resp.rendered_content
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_team_revoke_invite(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    inv = admin_team.invites.create(email='foo@example.org')
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-invite': str(inv.pk)
    }, follow=True)
    assert 'Admin team' in resp.rendered_content
    assert admin_user.email in resp.rendered_content
    assert not admin_team.invites.exists()


@pytest.mark.django_db
def test_team_remove_user(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    u = User.objects.create_user('dummy2@dummy.dummy', 'dummy')
    admin_team.members.add(u)

    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-member': u.pk
    }, follow=True)
    assert 'Admin team' in resp.rendered_content
    assert admin_user.email in resp.rendered_content
    assert u not in admin_team.members.all()


@pytest.mark.django_db
def test_team_remove_last_admin(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-member': admin_user.pk
    }, follow=True)
    assert 'alert-danger' in resp.rendered_content
    assert admin_user in admin_team.members.all()

    t2 = Team.objects.create(organizer=event.organizer, name='Admin team 2')
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-member': admin_user.pk
    }, follow=True)
    assert 'alert-danger' in resp.rendered_content
    assert admin_user in admin_team.members.all()

    t2.members.add(admin_user)
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-member': admin_user.pk
    }, follow=True)
    assert 'alert-danger' in resp.rendered_content
    assert admin_user in admin_team.members.all()

    t2.can_change_teams = True
    t2.save()
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'remove-member': admin_user.pk
    }, follow=True)
    assert 'alert-danger' not in resp.rendered_content
    assert admin_user not in admin_team.members.all()


@pytest.mark.django_db
def test_create_team(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/team/add', {
        'name': 'Foo',
        'can_create_events': 'on',
        'limit_events': str(event.pk),
        'can_change_event_settings': 'on'
    }, follow=True)
    t = Team.objects.last()
    assert t.can_change_event_settings
    assert t.can_create_events
    assert not t.can_change_organizer_settings
    assert list(t.limit_events.all()) == [event]
    assert list(t.members.all()) == [admin_user]


@pytest.mark.django_db
def test_update_team(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/team/{}/edit'.format(admin_team.pk), {
        'name': 'Admin',
        'can_change_teams': 'on',
        'limit_events': str(event.pk),
        'can_change_event_settings': 'on'
    }, follow=True)
    admin_team.refresh_from_db()
    assert admin_team.can_change_event_settings
    assert not admin_team.can_change_organizer_settings
    assert list(admin_team.limit_events.all()) == [event]


@pytest.mark.django_db
def test_update_last_team_to_be_no_admin(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.post('/control/organizer/dummy/team/{}/edit'.format(admin_team.pk), {
        'name': 'Admin',
        'can_change_event_settings': 'on'
    }, follow=True)
    assert 'alert-danger' in resp.rendered_content


@pytest.mark.django_db
def test_remove_team(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    t2 = Team.objects.create(organizer=event.organizer, name='Admin team 2')
    resp = client.post('/control/organizer/dummy/team/{}/delete'.format(t2.pk), {}, follow=True)
    assert Team.objects.count() == 1
    assert 'alert-success' in resp.rendered_content


@pytest.mark.django_db
def test_remove_last_admin_team(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')

    resp = client.post('/control/organizer/dummy/team/{}/delete'.format(admin_team.pk), {}, follow=True)
    assert Team.objects.count() == 1
    assert 'alert-danger' in resp.rendered_content


@pytest.mark.django_db
def test_resend_invalid_invite(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    djmail.outbox = []

    inv = admin_team.invites.create(email='foo@example.org')
    resp = client.post('/control/organizer/dummy/team/{}/'.format(admin_team.pk), {
        'resend-invite': inv.pk + 1
    }, follow=True)
    assert b'alert-danger' in resp.content
    assert b'Invalid invite selected.' in resp.content
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_invite_invalid_token(event, admin_team, client):
    i = admin_team.invites.create(email='foo@bar.com')
    resp = client.get('/control/invite/foo{}bar'.format(i.token), follow=True)
    assert b'alert-danger' in resp.content
    assert b'invalid link' in resp.content


@pytest.mark.django_db
def test_invite_existing_team_member(event, admin_team, client):
    u = User.objects.create_user('dummy2@dummy.dummy', 'dummy')
    admin_team.members.add(u)
    client.login(email='dummy2@dummy.dummy', password='dummy')
    i = admin_team.invites.create(email='foo@bar.com')
    resp = client.get('/control/invite/{}'.format(i.token), follow=True)
    assert b'alert-danger' in resp.content
    assert b'already are part of' in resp.content


@pytest.mark.django_db
def test_invite_authenticated(event, admin_team, client):
    u = User.objects.create_user('dummy2@dummy.dummy', 'dummy')
    client.login(email='dummy2@dummy.dummy', password='dummy')
    i = admin_team.invites.create(email='foo@bar.com')
    resp = client.get('/control/invite/{}'.format(i.token), follow=True)
    assert b'alert-success' in resp.content
    assert u in admin_team.members.all()
    assert not admin_team.invites.exists()


@pytest.mark.django_db
def test_invite_new_user(event, admin_team, client):
    i = admin_team.invites.create(email='foo@bar.com')
    resp = client.get('/control/invite/{}'.format(i.token), follow=True)
    assert b'<form' in resp.content
    resp = client.post('/control/invite/{}'.format(i.token), {
        'email': 'dummy@example.org',
        'password': 'asdsdgfgjh',
        'password_repeat': 'asdsdgfgjh'
    }, follow=True)

    assert b'alert-success' in resp.content
    assert admin_team.members.filter(email='dummy@example.org').exists()
    assert not admin_team.invites.exists()
