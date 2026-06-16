"""
Presale copy tests for pretix-sideburn-lottery.

Run from the monorepo:
    cd src && pytest ../pretix-sideburn-lottery/tests/test_presale_copy.py -v
"""
import datetime
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Event, Item, Organizer, Quota
from pretix_sideburn_lottery.services.presale import (
    get_lottery_date_display,
    get_sold_out_label,
)


@pytest.fixture
def presale_copy_env():
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

    return {"organizer": organizer, "event": event, "item": item}


def login_customer(client, organizer, email="test@example.com", password="test"):
    with scopes_disabled():
        customer = organizer.customers.create(
            email=email, is_verified=True, is_active=True
        )
        customer.set_password(password)
        customer.save()
    response = client.post(
        f"/{organizer.slug}/account/login",
        {"email": email, "password": password},
    )
    assert response.status_code == 302


@pytest.mark.django_db
def test_get_sold_out_label_without_lottery_date(presale_copy_env):
    event = presale_copy_env["event"]
    item = presale_copy_env["item"]

    with scopes_disabled():
        assert "lottery" in get_sold_out_label(event, item.pk).lower()


@pytest.mark.django_db
def test_get_sold_out_label_with_lottery_date(presale_copy_env):
    event = presale_copy_env["event"]
    item = presale_copy_env["item"]
    lottery_time = datetime.datetime(
        2026, 3, 15, 12, 0, tzinfo=datetime.timezone.utc
    )

    with scopes_disabled():
        event.settings.set(
            f"lottery_date_for_item_{item.pk}", lottery_time.isoformat()
        )
        label = get_sold_out_label(event, item.pk)
        date_display = get_lottery_date_display(event, item.pk)

    assert date_display in label
    assert "Ticket lottery held on" in label


@pytest.mark.django_db
def test_waitinglist_page_sideburn_copy(client, presale_copy_env):
    organizer = presale_copy_env["organizer"]
    event = presale_copy_env["event"]
    item = presale_copy_env["item"]

    login_customer(client, organizer)
    response = client.get(
        f"/{organizer.slug}/{event.slug}/waitinglist/?item={item.pk}"
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "How do tickets work for SideBurn?" in content
    assert "Register only once per person" in content


@pytest.mark.django_db
def test_event_page_sold_out_lottery_copy(client, presale_copy_env):
    organizer = presale_copy_env["organizer"]
    event = presale_copy_env["event"]

    login_customer(client, organizer)
    response = client.get(f"/{organizer.slug}/{event.slug}/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "assigned by lottery" in content
    assert "Register here" in content


@pytest.mark.django_db
def test_event_page_shows_lottery_date_when_set(client, presale_copy_env):
    organizer = presale_copy_env["organizer"]
    event = presale_copy_env["event"]
    item = presale_copy_env["item"]
    lottery_time = datetime.datetime(
        2026, 3, 15, 12, 0, tzinfo=datetime.timezone.utc
    )

    with scopes_disabled():
        event.settings.set(
            f"lottery_date_for_item_{item.pk}", lottery_time.isoformat()
        )
        date_display = get_lottery_date_display(event, item.pk)

    login_customer(client, organizer)
    response = client.get(f"/{organizer.slug}/{event.slug}/")
    assert response.status_code == 200
    assert date_display in response.content.decode()
