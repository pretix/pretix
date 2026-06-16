import pytest
from datetime import timedelta

from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix.base.models import (
    Event, Item, ItemVariation, Organizer, Quota, SubEvent, Voucher,
    WaitingListEntry,
)
from pretix_sideburn_lottery.services.rank import get_waiting_list_rank


@pytest.fixture
@scopes_disabled()
def rank_env():
    organizer = Organizer.objects.create(name="Dummy", slug="dummy")
    event = Event.objects.create(
        organizer=organizer,
        name="Dummy",
        slug="dummy",
        date_from=now(),
        live=True,
        plugins="pretix_sideburn_lottery",
    )
    quota = Quota.objects.create(name="Test", size=2, event=event)
    item1 = Item.objects.create(
        event=event, name="Ticket", default_price=23, admission=True
    )
    item2 = Item.objects.create(event=event, name="T-Shirt", default_price=23)
    item3 = Item.objects.create(event=event, name="Goodie", default_price=23)
    var1 = ItemVariation.objects.create(item=item2, value="S")
    ItemVariation.objects.create(item=item2, value="M")
    ItemVariation.objects.create(item=item3, value="Fancy")
    quota.items.add(item1)

    return {
        "organizer": organizer,
        "event": event,
        "item1": item1,
        "item2": item2,
        "item3": item3,
        "var1": var1,
    }


@pytest.mark.django_db
def test_get_rank_basic(rank_env):
    event = rank_env["event"]
    item1 = rank_env["item1"]
    with scope(organizer=rank_env["organizer"]):
        entries = [
            WaitingListEntry.objects.create(
                event=event, item=item1, email=f"user{i}@bar.com"
            )
            for i in range(5)
        ]

        assert get_waiting_list_rank(entries[0]) == 1
        assert get_waiting_list_rank(entries[1]) == 2
        assert get_waiting_list_rank(entries[4]) == 5


@pytest.mark.django_db
def test_get_rank_returns_zero_for_valid_voucher(rank_env):
    event = rank_env["event"]
    item1 = rank_env["item1"]
    with scope(organizer=rank_env["organizer"]):
        wle = WaitingListEntry.objects.create(
            event=event, item=item1, email="user@bar.com"
        )
        assert get_waiting_list_rank(wle) != 0

        v = Voucher.objects.create(
            event=event,
            item=item1,
            max_usages=1,
            redeemed=0,
            valid_until=now() + timedelta(days=1),
        )
        wle.voucher = v
        wle.save()

        assert get_waiting_list_rank(wle) == 0


@pytest.mark.django_db
def test_get_rank_returns_none_for_redeemed_voucher(rank_env):
    event = rank_env["event"]
    item1 = rank_env["item1"]
    with scope(organizer=rank_env["organizer"]):
        wle = WaitingListEntry.objects.create(
            event=event, item=item1, email="user@bar.com"
        )
        assert get_waiting_list_rank(wle) == 1

        v = Voucher.objects.create(
            event=event, item=item1, max_usages=1, redeemed=1
        )
        wle.voucher = v
        wle.save()

        assert get_waiting_list_rank(wle) is None


@pytest.mark.django_db
def test_get_rank_returns_none_for_expired_voucher(rank_env):
    event = rank_env["event"]
    item1 = rank_env["item1"]
    with scope(organizer=rank_env["organizer"]):
        wle = WaitingListEntry.objects.create(
            event=event, item=item1, email="user@bar.com"
        )
        v = Voucher.objects.create(
            event=event,
            item=item1,
            max_usages=1,
            redeemed=0,
            valid_until=now() - timedelta(days=1),
        )
        wle.voucher = v
        wle.save()

        assert get_waiting_list_rank(wle) is None


@pytest.mark.django_db
def test_get_rank_includes_unredeemed_voucher_holders_in_count(rank_env):
    event = rank_env["event"]
    item1 = rank_env["item1"]
    with scope(organizer=rank_env["organizer"]):
        wle1 = WaitingListEntry.objects.create(
            event=event, item=item1, email="user1@bar.com"
        )
        v = Voucher.objects.create(
            event=event,
            item=item1,
            max_usages=1,
            redeemed=0,
            valid_until=now() + timedelta(days=1),
        )
        wle1.voucher = v
        wle1.save()

        wle2 = WaitingListEntry.objects.create(
            event=event, item=item1, email="user2@bar.com"
        )

        assert get_waiting_list_rank(wle1) == 0
        assert get_waiting_list_rank(wle2) == 2


@pytest.mark.django_db
def test_get_rank_excludes_redeemed_expired_from_count(rank_env):
    event = rank_env["event"]
    item1 = rank_env["item1"]
    with scope(organizer=rank_env["organizer"]):
        wle1 = WaitingListEntry.objects.create(
            event=event, item=item1, email="user1@bar.com"
        )
        v_expired = Voucher.objects.create(
            event=event,
            item=item1,
            max_usages=1,
            redeemed=0,
            valid_until=now() - timedelta(days=1),
        )
        wle1.voucher = v_expired
        wle1.save()

        wle2 = WaitingListEntry.objects.create(
            event=event, item=item1, email="user2@bar.com"
        )
        v_redeemed = Voucher.objects.create(
            event=event, item=item1, max_usages=1, redeemed=1
        )
        wle2.voucher = v_redeemed
        wle2.save()

        wle3 = WaitingListEntry.objects.create(
            event=event, item=item1, email="user3@bar.com"
        )

        assert get_waiting_list_rank(wle1) is None
        assert get_waiting_list_rank(wle2) is None
        assert get_waiting_list_rank(wle3) == 1


@pytest.mark.django_db
def test_get_rank_ordering(rank_env):
    event = rank_env["event"]
    item1 = rank_env["item1"]
    with scope(organizer=rank_env["organizer"]):
        wle1 = WaitingListEntry.objects.create(
            event=event, item=item1, email="user1@bar.com", priority=10
        )
        wle2 = WaitingListEntry.objects.create(
            event=event, item=item1, email="user2@bar.com", priority=5
        )
        wle3 = WaitingListEntry.objects.create(
            event=event, item=item1, email="user3@bar.com", priority=10
        )

        assert get_waiting_list_rank(wle1) == 1
        assert get_waiting_list_rank(wle2) == 3
        assert get_waiting_list_rank(wle3) == 2


@pytest.mark.django_db
def test_get_rank_subevent(rank_env):
    event = rank_env["event"]
    item1 = rank_env["item1"]
    with scope(organizer=rank_env["organizer"]):
        subevent1 = SubEvent.objects.create(
            event=event, name="Day 1", date_from=now()
        )
        subevent2 = SubEvent.objects.create(
            event=event, name="Day 2", date_from=now()
        )

        wle1 = WaitingListEntry.objects.create(
            event=event,
            item=item1,
            email="user1@bar.com",
            subevent=subevent1,
        )
        wle2 = WaitingListEntry.objects.create(
            event=event,
            item=item1,
            email="user2@bar.com",
            subevent=subevent1,
        )
        wle3 = WaitingListEntry.objects.create(
            event=event,
            item=item1,
            email="user3@bar.com",
            subevent=subevent2,
        )

        assert get_waiting_list_rank(wle1) == 1
        assert get_waiting_list_rank(wle2) == 2
        assert get_waiting_list_rank(wle3) == 1


@pytest.mark.django_db
def test_get_rank_item_variation(rank_env):
    event = rank_env["event"]
    item1 = rank_env["item1"]
    item2 = rank_env["item2"]
    var1 = rank_env["var1"]
    with scope(organizer=rank_env["organizer"]):
        wle1 = WaitingListEntry.objects.create(
            event=event, item=item1, email="user1@bar.com"
        )
        wle2 = WaitingListEntry.objects.create(
            event=event,
            item=item2,
            variation=var1,
            email="user2@bar.com",
        )
        wle3 = WaitingListEntry.objects.create(
            event=event,
            item=item2,
            variation=var1,
            email="user3@bar.com",
        )

        assert get_waiting_list_rank(wle1) == 1
        assert get_waiting_list_rank(wle2) == 1
        assert get_waiting_list_rank(wle3) == 2


@pytest.mark.django_db
def test_waiting_list_position_placeholder(rank_env):
    from pretix.base.email import get_email_context

    event = rank_env["event"]
    item1 = rank_env["item1"]
    with scope(organizer=rank_env["organizer"]):
        entry = WaitingListEntry.objects.create(
            event=event, item=item1, email="user@bar.com"
        )
        ctx = get_email_context(event=event, waiting_list_entry=entry)

    assert ctx["waiting_list_position"] == "1"
