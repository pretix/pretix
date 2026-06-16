"""
Presale waiting-list rank display tests for pretix-sideburn-lottery.

Run from the monorepo:
    cd src && pytest ../pretix-sideburn-lottery/tests/test_presale_rank.py -v
"""
import datetime
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, Item, Organizer, Quota, Team, User, WaitingListEntry,
)
from pretix_sideburn_lottery.views.presale import get_waiting_list_ranks


@pytest.fixture
def presale_rank_env():
    organizer = Organizer.objects.create(name="CCC", slug="ccc")
    organizer.settings.customer_accounts = True
    organizer.save()

    event = Event.objects.create(
        organizer=organizer,
        name="30C3",
        slug="30c3",
        date_from=datetime.datetime(
            now().year + 1, 12, 26, 14, 0, tzinfo=datetime.timezone.utc
        ),
        live=True,
        sales_channels=["web", "bar"],
        plugins="pretix_sideburn_lottery",
    )
    event.settings.set("waiting_list_enabled", True)

    quota = Quota.objects.create(event=event, name="Quota", size=0)
    item = Item.objects.create(
        event=event,
        name="Early-bird ticket",
        default_price=Decimal("12.00"),
        active=True,
    )
    quota.items.add(item)

    user = User.objects.create_user("admin@example.com", "admin")
    team = Team.objects.create(
        organizer=organizer, can_view_orders=True, can_change_orders=True
    )
    team.members.add(user)
    team.limit_events.add(event)

    return {
        "organizer": organizer,
        "event": event,
        "item": item,
        "user": user,
    }


def login_customer(client, organizer, email="test@example.com", password="test"):
    response = client.post(
        f"/{organizer.slug}/account/login",
        {"email": email, "password": password},
    )
    assert response.status_code == 302


def create_customer(organizer, email="test@example.com", password="test"):
    customer = organizer.customers.create(
        email=email, is_verified=True, is_active=True
    )
    customer.set_password(password)
    customer.save()
    return customer


@pytest.mark.django_db
def test_get_waiting_list_ranks_single_product(presale_rank_env):
    event = presale_rank_env["event"]
    item = presale_rank_env["item"]

    with scopes_disabled():
        WaitingListEntry.objects.create(
            event=event, item=item, email="test@example.com"
        )
        ranks = get_waiting_list_ranks(event, "test@example.com")
    assert len(ranks) == 1
    assert ranks[0]["item_name"] == "Early-bird ticket"
    assert ranks[0]["rank"] == 1
    assert ranks[0]["lottery_run"] is False


@pytest.mark.django_db
def test_get_waiting_list_ranks_multiple_products(presale_rank_env):
    event = presale_rank_env["event"]
    item = presale_rank_env["item"]

    with scopes_disabled():
        item2 = Item.objects.create(
            event=event,
            name="VIP ticket",
            default_price=Decimal("50.00"),
            active=True,
        )
        Quota.objects.get(event=event).items.add(item2)
        WaitingListEntry.objects.create(
            event=event, item=item, email="test@example.com"
        )
        WaitingListEntry.objects.create(
            event=event, item=item2, email="test@example.com"
        )
        ranks = get_waiting_list_ranks(event, "test@example.com")
    assert len(ranks) == 2
    assert {r["item_name"] for r in ranks} == {"Early-bird ticket", "VIP ticket"}


@pytest.mark.django_db
def test_get_waiting_list_ranks_with_voucher(presale_rank_env):
    event = presale_rank_env["event"]
    item = presale_rank_env["item"]

    with scopes_disabled():
        voucher = event.vouchers.create(
            item=item,
            block_quota=True,
            valid_until=now() + datetime.timedelta(days=5),
        )
        WaitingListEntry.objects.create(
            event=event,
            item=item,
            email="test@example.com",
            voucher=voucher,
        )
        ranks = get_waiting_list_ranks(event, "test@example.com")
    assert len(ranks) == 1
    assert ranks[0]["rank"] == 0
    assert ranks[0]["voucher_code"] == voucher.code


@pytest.mark.django_db
def test_get_waiting_list_ranks_no_entries(presale_rank_env):
    with scopes_disabled():
        ranks = get_waiting_list_ranks(presale_rank_env["event"], "test@example.com")
    assert ranks == []


@pytest.mark.django_db
def test_presale_rank_display_single_product(client, presale_rank_env):
    organizer = presale_rank_env["organizer"]
    event = presale_rank_env["event"]
    item = presale_rank_env["item"]

    with scopes_disabled():
        create_customer(organizer)
        WaitingListEntry.objects.create(
            event=event, item=item, email="test@example.com"
        )

    login_customer(client, organizer)
    response = client.get(f"/{organizer.slug}/{event.slug}/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Check my spot in line" in content
    assert "Early-bird ticket" in content
    assert "lottery hasn" in content


@pytest.mark.django_db
def test_presale_rank_display_no_entries(client, presale_rank_env):
    organizer = presale_rank_env["organizer"]
    event = presale_rank_env["event"]

    with scopes_disabled():
        create_customer(organizer)

    login_customer(client, organizer)
    response = client.get(f"/{organizer.slug}/{event.slug}/")
    assert response.status_code == 200
    assert "You are not on the waiting list for this event." in response.content.decode()


@pytest.mark.django_db
def test_presale_rank_display_after_lottery(client, presale_rank_env):
    organizer = presale_rank_env["organizer"]
    event = presale_rank_env["event"]
    item = presale_rank_env["item"]
    user = presale_rank_env["user"]

    with scopes_disabled():
        create_customer(organizer)
        for i in range(3):
            WaitingListEntry.objects.create(
                event=event,
                item=item,
                email=f"other{i}@example.com",
            )
        WaitingListEntry.objects.create(
            event=event, item=item, email="test@example.com"
        )

    login_customer(client, organizer)
    response = client.get(f"/{organizer.slug}/{event.slug}/")
    assert response.status_code == 200
    assert "lottery hasn" in response.content.decode()

    client.logout()
    client.login(email=user.email, password="admin")
    response = client.get(
        f"/control/event/{organizer.slug}/{event.slug}/sideburn-lottery/run/?item={item.pk}"
    )
    assert response.status_code == 200

    client.logout()
    login_customer(client, organizer)
    response = client.get(f"/{organizer.slug}/{event.slug}/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "in line" in content
    assert "lottery hasn" not in content
