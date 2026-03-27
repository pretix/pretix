from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils.timezone import make_aware, now
from django_scopes import scope
from freezegun import freeze_time

from pretix.base.models import Event, Item, Order, OrderPosition, Organizer
from pretix.base.models.cancellation import CancellationRule, Ruling
from pretix.base.models.cancellation import CheckRes
from pretix.base.models.cancellation import OrderDiff

NOW = now()
DAYS_UNTIL_EVENT=60
EVENT_START = NOW+timedelta(days=DAYS_UNTIL_EVENT)



@pytest.fixture()
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy', plugins='pretix.plugins.banktransfer')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=EVENT_START,
        plugins='pretix.plugins.banktransfer'
    )
    return event

@pytest.fixture()
def item1(event):
    return Item.objects.create(event=event, name='Early-bird item1',
                                 default_price=Decimal('23.00'), admission=True)

@pytest.fixture()
def order(event):
    return Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING, locale='en',
        datetime=NOW,
        total=0,
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
    )


@pytest.mark.django_db
def test_status_rule(event, item1, order):
    with scope(organizer=event.organizer, event=event):
        op = OrderPosition.objects.create(
            order=order, item=item1, variation=None,
            price=Decimal("0.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
        )

        cancellation_rule = CancellationRule.objects.create(
            organizer=event.organizer, event=event,
            allowed_if_in_order_status=Order.STATUS_PENDING
        )
        cancellation_rule.items.set([item1])

        diff = OrderDiff.cancel_all(order)

        assert cancellation_rule._check_order_status(diff=diff, order_position=op) == {
            'ORDER_STATUS': CheckRes(
                cancellation_possible=True,
                reason="Order in required status: 'n'",
            ),
        }

        cancellation_rule = CancellationRule.objects.create(
            organizer=event.organizer, event=event,
            allowed_if_in_order_status=Order.STATUS_PAID
        )
        cancellation_rule.items.set([item1])

        assert cancellation_rule._check_order_status(diff=diff, order_position=op) == {
            'ORDER_STATUS': CheckRes(
                cancellation_possible=False,
                reason="Order in status 'n' cannot be canceled",
            ),
        }


@pytest.mark.django_db
def test_timing(event, item1, order):
    with scope(organizer=event.organizer, event=event):
        order.status = Order.STATUS_PAID
        order.save()

        OrderPosition.objects.create(
            order=order, item=item1, variation=None,
            price=Decimal("0.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
        )

        cr1 = CancellationRule.objects.create(
            organizer=event.organizer, event=event,
            allowed_until=now() + timedelta(hours=1),
        )
        cr1.items.set([item1])


        diff = OrderDiff.cancel_all(order)

        with freeze_time(now()):
            possible, verdicts = CancellationRule.objects.all().cancellation_possible(diff)
            assert possible == True

        with freeze_time(now()+timedelta(hours=2)):
            possible, verdicts=CancellationRule.objects.all().cancellation_possible(diff)
            assert possible == False


@pytest.mark.django_db
def test_multiple_limits(event, item1, order):
    with (scope(organizer=event.organizer, event=event)):
        order.status = Order.STATUS_PAID
        order.save()

        OrderPosition.objects.create(
            order=order, item=item1, variation=None,
            price=Decimal("100.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
        )

        # free in the first hour after booking
        cr1=CancellationRule.objects.create(
            organizer=event.organizer, event=event,
            allowed_until=NOW + timedelta(hours=1),
        )
        cr1.items.set([item1])

        # free until 30 days before event
        cr2 = CancellationRule.objects.create(
            organizer=event.organizer, event=event,
            allowed_until=EVENT_START - timedelta(days=30),
        )
        cr2.items.set([item1])

        # 50% until 14 days before event
        cr3 = CancellationRule.objects.create(
            organizer=event.organizer, event=event,
            allowed_until=EVENT_START - timedelta(days=14),
            fee_percentage_per_item=Decimal(50.0)
        )
        cr3.items.set([item1])

        # 80% until 7 days before event
        cr4 = CancellationRule.objects.create(
            organizer=event.organizer, event=event,
            allowed_until=EVENT_START - timedelta(days=7),
            fee_percentage_per_item=Decimal(80.0)
        )
        cr4.items.set([item1])

        # 100% until 1 day before event
        cr5 = CancellationRule.objects.create(
            organizer=event.organizer, event=event,
            allowed_until=EVENT_START - timedelta(days=1),
            fee_percentage_per_item=Decimal(100)
        )
        cr5.items.set([item1])

        # Cancellation is not allowed at all, but rule doesn't match the item
        CancellationRule.objects.create(
            organizer=event.organizer, event=event,
            allowed_until=NOW,
            fee_percentage_per_item=Decimal(100)
        )


        diff = OrderDiff.cancel_all(order)

        possible_trace = []
        cost_trace = []

        for days in range(DAYS_UNTIL_EVENT):
            today = NOW + timedelta(days=days)
            with freeze_time(today):
                possible, verdicts=CancellationRule.objects.all().cancellation_possible(
                    diff)
                possible_trace.append(possible)
                cost_trace.append(verdicts[0].total_fee)

        assert possible_trace == [True] * 59 + [False]
        assert cost_trace == [Decimal("0.0000")] * 30 + \
                             [Decimal("50.0000")] * 16 + \
                             [Decimal("80.0000")] * 7 + \
                             [Decimal("100.0000")] * 6 + \
                             [Decimal("0.0000")]




@pytest.mark.django_db
def test_cancellation_rule_query_set(event, item1, order):
    with scope(organizer=event.organizer, event=event):
        OrderPosition.objects.create(
            order=order, item=item1, variation=None,
            price=Decimal("0.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
        )

        cr1 = CancellationRule.objects.create(
            organizer=event.organizer, event=event,
            allowed_if_in_order_status=Order.STATUS_PENDING, fee_absolute_per_order=Decimal('10.00'),
        )
        cr1.items.set([item1])


        cr2 = CancellationRule.objects.create(
            organizer=event.organizer, event=event,
            allowed_if_in_order_status=Order.STATUS_PAID
        )
        cr2.items.set([item1])

        diff = OrderDiff.cancel_all(order)

        possible, verdicts = CancellationRule.objects.all().cancellation_possible(diff)

        assert  possible == True
