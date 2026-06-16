import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Event, Item, Organizer, Quota


@pytest.fixture
@scopes_disabled()
def lottery_env():
    """Organizer + event with lottery plugin enabled and waiting list active."""
    organizer = Organizer.objects.create(name="Sideburn Test", slug="sideburntest")
    organizer.settings.customer_accounts = True
    organizer.settings.customer_accounts_native = True

    event = Event.objects.create(
        organizer=organizer,
        name="Test Event",
        slug="testevent",
        date_from=now(),
        live=True,
        plugins="pretix_sideburn_lottery",
    )
    event.settings.set("waiting_list_enabled", True)

    quota = Quota.objects.create(event=event, name="Tickets", size=0)
    item = Item.objects.create(
        event=event,
        name="General Admission",
        default_price=100,
        admission=True,
        active=True,
    )
    quota.items.add(item)

    return {
        "organizer": organizer,
        "event": event,
        "item": item,
        "quota": quota,
    }
