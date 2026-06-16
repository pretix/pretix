"""
Admin lottery run/revert tests for pretix-sideburn-lottery.

Run from the monorepo:
    cd src && pytest ../pretix-sideburn-lottery/tests/test_admin_lottery.py -v
"""
import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, Item, Organizer, Quota, Team, User, Voucher, WaitingListEntry,
)


def get_priorities(event, item):
    return list(
        WaitingListEntry.objects.filter(event=event, item=item, voucher__isnull=True)
        .order_by("pk")
        .values_list("priority", flat=True)
    )


@pytest.fixture
def admin_lottery_env():
    organizer = Organizer.objects.create(name="Dummy", slug="dummy")
    event = Event.objects.create(
        organizer=organizer,
        name="Dummy",
        slug="dummy",
        date_from=now(),
        plugins="pretix_sideburn_lottery",
    )
    user = User.objects.create_user("dummy@dummy.dummy", "dummy")
    item1 = Item.objects.create(
        event=event, name="Ticket", default_price=23, admission=True
    )
    item2 = Item.objects.create(
        event=event, name="Ticket B", default_price=23, admission=True
    )

    for i in range(5):
        WaitingListEntry.objects.create(
            event=event, item=item1, email="foo{}@bar.com".format(i)
        )
    v = Voucher.objects.create(
        item=item1, event=event, block_quota=True, redeemed=1
    )
    WaitingListEntry.objects.create(
        event=event, item=item1, email="success@example.org", voucher=v
    )

    team = Team.objects.create(
        organizer=organizer, can_view_orders=True, can_change_orders=True
    )
    team.members.add(user)
    team.limit_events.add(event)

    return {
        "organizer": organizer,
        "event": event,
        "user": user,
        "item1": item1,
        "item2": item2,
    }


@pytest.mark.django_db
def test_lottery_requires_product(client, admin_lottery_env):
    client.login(email="dummy@dummy.dummy", password="dummy")

    response = client.get(
        "/control/event/dummy/dummy/sideburn-lottery/run/"
    )

    assert response.status_code == 302
    assert "/control/event/dummy/dummy/waitinglist/" in response.url

    response = client.get(response.url)
    assert "You must select a product" in response.content.decode()


@pytest.mark.django_db
def test_lottery_with_single_product(client, admin_lottery_env):
    client.login(email="dummy@dummy.dummy", password="dummy")
    event = admin_lottery_env["event"]
    item1 = admin_lottery_env["item1"]

    with scopes_disabled():
        initial_priorities = get_priorities(event, item1)

    response = client.get(
        "/control/event/dummy/dummy/sideburn-lottery/run/?item=%d" % item1.pk
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"

    with scopes_disabled():
        after_priorities = get_priorities(event, item1)

    assert initial_priorities != after_priorities


@pytest.mark.django_db
def test_lottery_isolation(client, admin_lottery_env):
    client.login(email="dummy@dummy.dummy", password="dummy")
    event = admin_lottery_env["event"]
    item1 = admin_lottery_env["item1"]
    item2 = admin_lottery_env["item2"]

    with scopes_disabled():
        for i in range(3):
            WaitingListEntry.objects.create(
                event=event, item=item2, email="item2foo{}@bar.com".format(i)
            )

        initial_priorities_item1 = get_priorities(event, item1)
        initial_priorities_item2 = get_priorities(event, item2)

    response = client.get(
        "/control/event/dummy/dummy/sideburn-lottery/run/?item=%d" % item1.pk
    )
    assert response.status_code == 200

    with scopes_disabled():
        after_priorities_item1 = get_priorities(event, item1)
        after_priorities_item2 = get_priorities(event, item2)

    assert initial_priorities_item1 != after_priorities_item1
    assert initial_priorities_item2 == after_priorities_item2

    item1_after_first_lottery = after_priorities_item1.copy()

    response = client.get(
        "/control/event/dummy/dummy/sideburn-lottery/run/?item=%d" % item2.pk
    )
    assert response.status_code == 200

    with scopes_disabled():
        final_priorities_item1 = get_priorities(event, item1)
        final_priorities_item2 = get_priorities(event, item2)

    assert final_priorities_item1 == item1_after_first_lottery
    assert initial_priorities_item2 != final_priorities_item2


@pytest.mark.django_db
def test_lottery_sets_item_date(client, admin_lottery_env):
    client.login(email="dummy@dummy.dummy", password="dummy")
    event = admin_lottery_env["event"]
    item1 = admin_lottery_env["item1"]

    assert not event.settings.get(f"lottery_date_for_item_{item1.pk}")

    response = client.get(
        "/control/event/dummy/dummy/sideburn-lottery/run/?item=%d" % item1.pk
    )
    assert response.status_code == 200

    event.settings.flush()
    assert event.settings.get(f"lottery_date_for_item_{item1.pk}")


@pytest.mark.django_db
def test_lottery_revert_clears_item_date(client, admin_lottery_env):
    client.login(email="dummy@dummy.dummy", password="dummy")
    event = admin_lottery_env["event"]
    item1 = admin_lottery_env["item1"]

    client.get(
        "/control/event/dummy/dummy/sideburn-lottery/run/?item=%d" % item1.pk
    )
    event.settings.flush()
    assert event.settings.get(f"lottery_date_for_item_{item1.pk}")

    response = client.get(
        "/control/event/dummy/dummy/sideburn-lottery/revert/?item=%d" % item1.pk
    )
    assert response.status_code == 200

    event.settings.flush()
    assert not event.settings.get(f"lottery_date_for_item_{item1.pk}")
