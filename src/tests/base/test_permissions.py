import pytest
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
def user():
    return User.objects.create_user('dummy@dummy.dummy', 'dummy')


@pytest.mark.django_db
def test_invalid_permission(event, user):
    team = Team.objects.create(organizer=event.organizer)
    with pytest.raises(ValueError):
        team.has_permission('FOOOOOOBAR')


@pytest.mark.django_db
def test_any_event_permission_limited(event, user):
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event)

    team = Team.objects.create(organizer=event.organizer)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event)

    team.members.add(user)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event)
    assert not team.permission_for_event(event)

    team.limit_events.add(event)
    user._teamcache = {}
    assert team.permission_for_event(event)
    assert user.has_event_permission(event.organizer, event)


@pytest.mark.django_db
def test_any_event_permission_all(event, user):
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event)

    team = Team.objects.create(organizer=event.organizer)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event)

    team.members.add(user)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event)
    assert not team.permission_for_event(event)

    team.all_events = True
    team.save()
    user._teamcache = {}
    assert team.permission_for_event(event)
    assert user.has_event_permission(event.organizer, event)


@pytest.mark.django_db
def test_specific_event_permission_limited(event, user):
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'can_change_orders')

    team = Team.objects.create(organizer=event.organizer, can_change_orders=True)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'can_change_orders')

    team.members.add(user)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'can_change_orders')

    team.limit_events.add(event)
    user._teamcache = {}
    assert user.has_event_permission(event.organizer, event, 'can_change_orders')
    assert not user.has_event_permission(event.organizer, event, 'can_change_event_settings')

    team.can_change_orders = False
    team.save()
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'can_change_orders')


@pytest.mark.django_db
def test_specific_event_permission_all(event, user):
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'can_change_orders')

    team = Team.objects.create(organizer=event.organizer, can_change_orders=True)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'can_change_orders')

    team.members.add(user)
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'can_change_orders')

    team.all_events = True
    team.save()
    user._teamcache = {}
    assert user.has_event_permission(event.organizer, event, 'can_change_orders')

    team.can_change_orders = False
    team.save()
    user._teamcache = {}
    assert not user.has_event_permission(event.organizer, event, 'can_change_orders')


@pytest.mark.django_db
def test_event_permissions_multiple_teams(event, user):
    team1 = Team.objects.create(organizer=event.organizer, can_change_orders=True, all_events=True)
    team2 = Team.objects.create(organizer=event.organizer, can_change_vouchers=True)
    team3 = Team.objects.create(organizer=event.organizer, can_change_event_settings=True)
    event2 = Event.objects.create(
        organizer=event.organizer, name='Dummy', slug='dummy',
        date_from=now()
    )
    team1.members.add(user)
    team2.members.add(user)
    team3.members.add(user)
    team2.limit_events.add(event)
    team3.limit_events.add(event2)

    assert user.has_event_permission(event.organizer, event, 'can_change_orders')
    assert user.has_event_permission(event.organizer, event, 'can_change_vouchers')
    assert not user.has_event_permission(event.organizer, event, 'can_change_event_settings')
    assert user.get_event_permission_set(event.organizer, event) == {'can_change_orders', 'can_change_vouchers'}
    assert user.get_event_permission_set(event.organizer, event2) == {'can_change_orders', 'can_change_event_settings',
                                                                      'can_change_settings'}


@pytest.mark.django_db
def test_any_organizer_permission(event, user):
    user._teamcache = {}
    assert not user.has_organizer_permission(event.organizer)

    team = Team.objects.create(organizer=event.organizer)
    user._teamcache = {}
    assert not user.has_organizer_permission(event.organizer)

    team.members.add(user)
    user._teamcache = {}
    assert user.has_organizer_permission(event.organizer)


@pytest.mark.django_db
def test_specific_organizer_permission(event, user):
    user._teamcache = {}
    assert not user.has_organizer_permission(event.organizer, 'can_create_events')

    team = Team.objects.create(organizer=event.organizer, can_create_events=True)
    user._teamcache = {}
    assert not user.has_organizer_permission(event.organizer, 'can_create_events')

    team.members.add(user)
    user._teamcache = {}
    assert user.has_organizer_permission(event.organizer, 'can_create_events')


@pytest.mark.django_db
def test_organizer_permissions_multiple_teams(event, user):
    team1 = Team.objects.create(organizer=event.organizer, can_change_organizer_settings=True)
    team2 = Team.objects.create(organizer=event.organizer, can_create_events=True)
    team1.members.add(user)
    team2.members.add(user)
    orga2 = Organizer.objects.create(slug='d2', name='d2')
    team3 = Team.objects.create(organizer=orga2, can_change_teams=True)
    team3.members.add(user)

    assert user.has_organizer_permission(event.organizer, 'can_create_events')
    assert user.has_organizer_permission(event.organizer, 'can_change_organizer_settings')
    assert not user.has_organizer_permission(event.organizer, 'can_change_teams')
    assert user.get_organizer_permission_set(event.organizer) == {'can_create_events', 'can_change_organizer_settings'}
    assert user.get_organizer_permission_set(orga2) == {'can_change_teams'}


@pytest.mark.django_db
def test_superuser(event, user):
    user.is_superuser = True
    user.save()

    assert user.has_organizer_permission(event.organizer)
    assert user.has_organizer_permission(event.organizer, 'can_create_events')
    assert user.has_event_permission(event.organizer, event)
    assert user.has_event_permission(event.organizer, event, 'can_change_event_settings')

    assert 'arbitrary' in user.get_event_permission_set(event.organizer, event)
    assert 'arbitrary' in user.get_organizer_permission_set(event.organizer)

    assert event in user.get_events_with_any_permission()


@pytest.mark.django_db
def test_list_of_events(event, user):
    orga2 = Organizer.objects.create(slug='d2', name='d2')
    event2 = Event.objects.create(
        organizer=event.organizer, name='Dummy', slug='dummy2',
        date_from=now()
    )
    event3 = Event.objects.create(
        organizer=orga2, name='Dummy', slug='dummy3',
        date_from=now()
    )
    event4 = Event.objects.create(
        organizer=orga2, name='Dummy', slug='dummy4',
        date_from=now()
    )

    assert not user.get_events_with_any_permission()

    team1 = Team.objects.create(organizer=event.organizer, can_change_orders=True, all_events=True)
    team2 = Team.objects.create(organizer=event.organizer, can_change_vouchers=True)
    team3 = Team.objects.create(organizer=orga2, can_change_event_settings=True)
    team1.members.add(user)
    team2.members.add(user)
    team3.members.add(user)
    team2.limit_events.add(event)
    team3.limit_events.add(event3)

    events = list(user.get_events_with_any_permission())
    assert event in events
    assert event2 in events
    assert event3 in events
    assert event4 not in events

    events = list(user.get_events_with_permission('can_change_event_settings'))
    assert event not in events
    assert event2 not in events
    assert event3 in events
    assert event4 not in events

    admin = User.objects.get(is_superuser=True)
    assert set(event.get_users_with_any_permission()) == {user, admin}
    assert set(event2.get_users_with_any_permission()) == {user, admin}
    assert set(event3.get_users_with_any_permission()) == {user, admin}
    assert set(event4.get_users_with_any_permission()) == {admin}

    assert set(event.get_users_with_permission('can_change_event_settings')) == {admin}
    assert set(event2.get_users_with_permission('can_change_event_settings')) == {admin}
    assert set(event3.get_users_with_permission('can_change_event_settings')) == {user, admin}
    assert set(event4.get_users_with_permission('can_change_event_settings')) == {admin}
    assert set(event.get_users_with_permission('can_change_orders')) == {admin, user}
