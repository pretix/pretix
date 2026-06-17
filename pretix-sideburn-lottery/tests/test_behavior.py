"""
Phase 2.5 behavioral waiting-list tests for pretix-sideburn-lottery.

Run from the monorepo:
    cd src && pytest ../pretix-sideburn-lottery/tests/test_behavior.py -v
"""
from datetime import timedelta

import pytest
from django.core import mail as djmail
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix.base.models import (
    Event, Item, Organizer, Quota, User, Voucher, WaitingListEntry,
)
from pretix.base.models.waitinglist import WaitingListException
from pretix.control.signals import waitinglist_allow_delete_with_voucher
from pretix_sideburn_lottery.services.waitinglist import send_signup_confirmation


@pytest.fixture
@scopes_disabled()
def behavior_env():
    organizer = Organizer.objects.create(name="Dummy", slug="dummy")
    event = Event.objects.create(
        organizer=organizer,
        name="Dummy",
        slug="dummy",
        date_from=now(),
        live=True,
        plugins="pretix_sideburn_lottery",
    )
    quota = Quota.objects.create(name="Test", size=0, event=event)
    item = Item.objects.create(
        event=event, name="Ticket", default_price=23, admission=True
    )
    quota.items.add(item)
    return {"organizer": organizer, "event": event, "item": item, "quota": quota}


@pytest.mark.django_db
@scopes_disabled()
def test_send_voucher_ignores_quota_when_plugin_active(behavior_env):
    event = behavior_env["event"]
    item = behavior_env["item"]
    wle = WaitingListEntry.objects.create(
        event=event, item=item, email="foo@bar.com"
    )
    djmail.outbox = []
    wle.send_voucher()
    wle.refresh_from_db()
    assert wle.voucher
    assert wle.voucher.allow_ignore_quota is True
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
@scopes_disabled()
def test_send_voucher_respects_quota_without_plugin():
    organizer = Organizer.objects.create(name="Plain", slug="plain")
    event = Event.objects.create(
        organizer=organizer,
        name="Plain",
        slug="plain",
        date_from=now(),
        live=True,
    )
    quota = Quota.objects.create(name="Test", size=0, event=event)
    item = Item.objects.create(
        event=event, name="Ticket", default_price=23, admission=True
    )
    quota.items.add(item)
    wle = WaitingListEntry.objects.create(
        event=event, item=item, email="foo@bar.com"
    )
    with pytest.raises(WaitingListException):
        wle.send_voucher()


@pytest.mark.django_db
@scopes_disabled()
def test_signup_confirmation_email(behavior_env):
    event = behavior_env["event"]
    wle = WaitingListEntry.objects.create(
        event=event, item=behavior_env["item"], email="foo@bar.com"
    )
    djmail.outbox = []
    send_signup_confirmation(wle)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["foo@bar.com"]
    assert "lottery waiting list" in djmail.outbox[0].subject.lower()


@pytest.mark.django_db
@scopes_disabled()
def test_duplicate_allows_expired_unredeemed_voucher(behavior_env):
    event = behavior_env["event"]
    item = behavior_env["item"]
    v = Voucher.objects.create(
        event=event, valid_until=now() - timedelta(days=1), redeemed=0
    )
    WaitingListEntry.objects.create(
        event=event, item=item, email="foo@bar.com", voucher=v
    )
    wle = WaitingListEntry(event=event, item=item, email="foo@bar.com")
    wle.full_clean()


@pytest.mark.django_db
@scopes_disabled()
def test_duplicate_blocks_redeemed_voucher(behavior_env):
    event = behavior_env["event"]
    item = behavior_env["item"]
    v = Voucher.objects.create(
        event=event, valid_until=now() - timedelta(days=1), redeemed=1
    )
    WaitingListEntry.objects.create(
        event=event, item=item, email="foo@bar.com", voucher=v
    )
    wle = WaitingListEntry(event=event, item=item, email="foo@bar.com")
    with pytest.raises(ValidationError):
        wle.full_clean()


@pytest.mark.django_db
@scopes_disabled()
def test_duplicate_blocks_valid_unredeemed_voucher(behavior_env):
    event = behavior_env["event"]
    item = behavior_env["item"]
    v = Voucher.objects.create(
        event=event, valid_until=now() + timedelta(days=1), redeemed=0
    )
    WaitingListEntry.objects.create(
        event=event, item=item, email="foo@bar.com", voucher=v
    )
    wle = WaitingListEntry(event=event, item=item, email="foo@bar.com")
    with pytest.raises(ValidationError):
        wle.full_clean()


@pytest.mark.django_db
@scopes_disabled()
def test_allow_delete_with_voucher_signal(behavior_env):
    event = behavior_env["event"]
    responses = [
        response
        for receiver, response in waitinglist_allow_delete_with_voucher.send(
            event, request=None
        )
        if response
    ]
    assert responses == [True]


@pytest.mark.django_db
def test_delete_entry_with_voucher_when_plugin_active(client, behavior_env):
    organizer = behavior_env["organizer"]
    event = behavior_env["event"]
    item = behavior_env["item"]
    user = User.objects.create_user("admin@example.org", "admin")
    from pretix.base.models import Team

    team = Team.objects.create(
        organizer=organizer, can_view_orders=True, can_change_orders=True
    )
    team.members.add(user)
    team.limit_events.add(event)

    v = Voucher.objects.create(item=item, event=event, block_quota=True, redeemed=0)
    entry = WaitingListEntry.objects.create(
        event=event, item=item, email="assigned@example.org", voucher=v
    )

    client.login(email="admin@example.org", password="admin")
    with scope(organizer=organizer):
        response = client.post(
            f"/control/event/dummy/dummy/waitinglist/{entry.pk}/delete",
            follow=True,
        )
        assert response.status_code == 200
        assert not WaitingListEntry.objects.filter(pk=entry.pk).exists()
        # Deleting the entry does not delete the linked voucher (FK is on the entry).
        assert Voucher.objects.filter(pk=v.pk).exists()
