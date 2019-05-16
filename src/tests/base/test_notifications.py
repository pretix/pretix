from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail as djmail
from django.db import transaction
from django.utils.timezone import now

from pretix.base.models import (
    Event, Item, Order, OrderPosition, Organizer, User,
)


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


@pytest.fixture
def order(event):
    o = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING, locale='en',
        datetime=now(), expires=now() + timedelta(days=10),
        total=Decimal('46.00'),
    )
    tr19 = event.tax_rules.create(rate=Decimal('19.00'))
    ticket = Item.objects.create(event=event, name='Early-bird ticket', tax_rule=tr19,
                                 default_price=Decimal('23.00'), admission=True)
    OrderPosition.objects.create(
        order=o, item=ticket, variation=None,
        price=Decimal("23.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
    )
    return o


@pytest.fixture
def team(event):
    return event.organizer.teams.create(all_events=True, can_view_orders=True)


@pytest.fixture
def user(team):
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    team.members.add(user)
    return user


@pytest.fixture
def monkeypatch_on_commit(monkeypatch):
    monkeypatch.setattr("django.db.transaction.on_commit", lambda t: t())


@pytest.mark.django_db
def test_notification_trigger_event_specific(event, order, user, monkeypatch_on_commit):
    djmail.outbox = []
    user.notification_settings.create(
        method='mail', event=event, action_type='pretix.event.order.paid', enabled=True
    )
    with transaction.atomic():
        order.log_action('pretix.event.order.paid', {})
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject.endswith("DUMMY: Order FOO has been marked as paid.")


@pytest.mark.django_db
def test_notification_trigger_global(event, order, user, monkeypatch_on_commit):
    djmail.outbox = []
    user.notification_settings.create(
        method='mail', event=None, action_type='pretix.event.order.paid', enabled=True
    )
    with transaction.atomic():
        order.log_action('pretix.event.order.paid', {})
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_notification_trigger_global_wildcard(event, order, user, monkeypatch_on_commit):
    djmail.outbox = []
    user.notification_settings.create(
        method='mail', event=None, action_type='pretix.event.order.changed.*', enabled=True
    )
    with transaction.atomic():
        order.log_action('pretix.event.order.changed.item', {})
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_notification_enabled_global_ignored_specific(event, order, user, monkeypatch_on_commit):
    djmail.outbox = []
    user.notification_settings.create(
        method='mail', event=None, action_type='pretix.event.order.paid', enabled=True
    )
    user.notification_settings.create(
        method='mail', event=event, action_type='pretix.event.order.paid', enabled=False
    )
    with transaction.atomic():
        order.log_action('pretix.event.order.paid', {})
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_notification_ignore_same_user(event, order, user, monkeypatch_on_commit):
    djmail.outbox = []
    user.notification_settings.create(
        method='mail', event=event, action_type='pretix.event.order.paid', enabled=True
    )
    with transaction.atomic():
        order.log_action('pretix.event.order.paid', {}, user=user)
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_notification_ignore_insufficient_permissions(event, order, user, team, monkeypatch_on_commit):
    djmail.outbox = []
    team.can_view_orders = False
    team.save()
    user.notification_settings.create(
        method='mail', event=event, action_type='pretix.event.order.paid', enabled=True
    )
    with transaction.atomic():
        order.log_action('pretix.event.order.paid', {})
    assert len(djmail.outbox) == 0

# TODO: Test email content
