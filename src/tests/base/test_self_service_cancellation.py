from decimal import Decimal

from pretix.base.models.cancellation import CancellationRule
from pretix.base.models import Order, Event, OrderPosition, Organizer, Item
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from django.utils.timezone import make_aware, now
from django_scopes import scope

import pytest

from pretix.base.models.cancellation import Ruling


@pytest.fixture(scope='function')
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy', plugins='pretix.plugins.banktransfer')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(),
        plugins='pretix.plugins.banktransfer'
    )
    with scope(organizer=o):
        yield event

@pytest.fixture(scope="function")
def ticket(event):
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 default_price=Decimal('23.00'), admission=True)

    return ticket


@pytest.mark.django_db
def test_status_rule(event, ticket):
    o = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING, locale='en',
        datetime=now(), expires=now() + timedelta(days=10),
        total=0,
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
    )

    op = OrderPosition.objects.create(
        order=o, item=ticket, variation=None,
        price=Decimal("0.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
    )

    cancellation_rule = CancellationRule.objects.create(
        organizer=event.organizer, event=event, item=ticket,
        order_status=Order.STATUS_PENDING
    )

    assert cancellation_rule._rule_order_status(order_position=op) == {
        1: Ruling(
            cancellation_possible=True,
            reason="Order in required status: 'n'",
        ),
    }

    cancellation_rule = CancellationRule.objects.create(
        organizer=event.organizer, event=event, item=ticket,
        order_status=Order.STATUS_PAID
    )

    assert cancellation_rule._rule_order_status(order_position=op) == {
        2: Ruling(
            cancellation_possible=False,
            reason="Order in status 'n' cannot be canceled",
        ),
    }


@pytest.mark.django_db
def test_cancelation_rule_query_set(event, ticket):
    with scope(organizer=event.organizer, event=event):
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, locale='en',
            datetime=now(), expires=now() + timedelta(days=10),
            total=0,
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
        )

        op = OrderPosition.objects.create(
            order=o, item=ticket, variation=None,
            price=Decimal("0.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
        )

        cr1 = CancellationRule.objects.create(
            organizer=event.organizer, event=event, item=ticket,
            order_status=Order.STATUS_PENDING, fee_absolute_per_order=Decimal('10.00'),
        )

        cr2 = CancellationRule.objects.create(
            organizer=event.organizer, event=event, item=ticket,
            order_status=Order.STATUS_PAID
        )


        assert CancellationRule.objects.all().cancellation_possible(o) == True
