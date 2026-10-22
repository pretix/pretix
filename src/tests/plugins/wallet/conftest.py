from datetime import timedelta

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import Event, Order, Organizer, User


@pytest.fixture
def env():
    organizer = Organizer.objects.create(name="Dummy", slug="dummy")
    prop1 = organizer.meta_properties.get_or_create(name="Test")[0]
    prop2 = organizer.meta_properties.get_or_create(name="Website")[0]
    event = Event.objects.create(
        organizer=organizer, name="Dummy", slug="dummy", date_from=now(), plugins="pretix.plugins.wallet"
    )
    event.meta_values.update_or_create(property=prop1, defaults={"value": "*Beep*"})
    event.meta_values.update_or_create(
        property=prop2, defaults={"value": "https://example.com"}
    )
    user = User.objects.create_user("dummy@dummy.dummy", "dummy")
    user.email = "dummy@dummy.dummy"
    user.save()
    with scope(organizer=organizer):
        yield event, user, organizer


@pytest.fixture
def order(env):
    event, user, organizer = env
    o = Order.objects.create(
        code="FOO",
        event=event,
        email="dummy@dummy.test",
        status=Order.STATUS_PAID,
        datetime=now(),
        expires=now() + timedelta(days=10),
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
        total=23,
        locale="en",
    )
    ticket = event.items.create(
        name="Ticket",
        category=None,
        default_price=23,
        admission=True,
        personalized=True,
    )
    o.positions.create(item=ticket, price=23)
    return o
