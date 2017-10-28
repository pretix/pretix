from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now

from pretix.base.models import (
    Checkin, Event, Item, ItemAddOn, ItemCategory, LogEntry, Order,
    OrderPosition, Organizer, Team, User,
)
from pretix.control.views.dashboards import checkin_widget


@pytest.fixture
def dashboard_env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,tests.testdummy'
    )
    event.settings.set('ticketoutput_testdummy__enabled', True)
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    item_ticket = Item.objects.create(event=event, name="Ticket", default_price=23, admission=True)
    item_mascot = Item.objects.create(event=event, name="Mascot", default_price=10, admission=False)

    t = Team.objects.create(organizer=o, can_view_orders=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)

    event.settings.set('attendee_names_asked', True)
    event.settings.set('locales', ['en', 'de'])

    order_paid = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=33, payment_provider='banktransfer', locale='en'
    )
    OrderPosition.objects.create(
        order=order_paid,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name="Peter"
    )
    OrderPosition.objects.create(
        order=order_paid,
        item=item_mascot,
        variation=None,
        price=Decimal("10")
    )

    return event, user, o, order_paid, item_ticket, item_mascot


@pytest.mark.django_db
def test_dashboard(dashboard_env):
    c = checkin_widget(dashboard_env[0])
    assert '0/2' in c[0]['content']


@pytest.mark.django_db
def test_dashboard_pending_not_count(dashboard_env):
    c = checkin_widget(dashboard_env[0])
    order_pending = Order.objects.create(
        code='FOO', event=dashboard_env[0], email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, payment_provider='banktransfer', locale='en'
    )
    OrderPosition.objects.create(
        order=order_pending,
        item=dashboard_env[4],
        variation=None,
        price=Decimal("23"),
        attendee_name="NotPaid"
    )
    assert '0/2' in c[0]['content']


@pytest.mark.django_db
def test_dashboard_with_checkin(dashboard_env):
    op = OrderPosition.objects.get(
        order=dashboard_env[3],
        item=dashboard_env[4]
    )
    Checkin.objects.create(position=op)
    c = checkin_widget(dashboard_env[0])
    assert '1/2' in c[0]['content']


@pytest.mark.django_db
def test_dashboard_exclude_non_admission_item(dashboard_env):
    dashboard_env[0].settings.ticket_download_nonadm = False
    dashboard_env[0].save()
    c = checkin_widget(dashboard_env[0])
    assert '0/1' in c[0]['content']


@pytest.mark.django_db
def test_dashboard_exclude_non_admission_item_with_checkin(dashboard_env):
    dashboard_env[0].settings.ticket_download_nonadm = False
    dashboard_env[0].save()
    op = OrderPosition.objects.get(
        order=dashboard_env[3],
        item=dashboard_env[4]
    )
    Checkin.objects.create(position=op)
    c = checkin_widget(dashboard_env[0])
    assert '1/1' in c[0]['content']


@pytest.fixture
def checkin_list_env():
    # permission
    orga = Organizer.objects.create(name='Dummy', slug='dummy')
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    team = Team.objects.create(organizer=orga, can_view_orders=True, can_change_orders=True)
    team.members.add(user)

    # event
    event = Event.objects.create(
        organizer=orga, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,tests.testdummy'
    )
    event.settings.set('ticketoutput_testdummy__enabled', True)
    event.settings.set('attendee_names_asked', True)
    event.settings.set('locales', ['en', 'de'])
    team.limit_events.add(event)

    # item
    item_ticket = Item.objects.create(event=event, name="Ticket", default_price=23, admission=True)
    item_mascot = Item.objects.create(event=event, name="Mascot", default_price=10, admission=False)

    # order
    order_pending = Order.objects.create(
        code='PENDING', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, payment_provider='banktransfer', locale='en'
    )
    order_a1 = Order.objects.create(
        code='A1', event=event, email='a1dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=33, payment_provider='banktransfer', locale='en'
    )
    order_a2 = Order.objects.create(
        code='A2', event=event, email='a2dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, payment_provider='banktransfer', locale='en'
    )
    order_a3 = Order.objects.create(
        code='A3', event=event, email='a3dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, payment_provider='banktransfer', locale='en'
    )

    # order position
    op_pending_ticket = OrderPosition.objects.create(
        order=order_pending,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name="Pending"
    )
    op_a1_ticket = OrderPosition.objects.create(
        order=order_a1,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name="A1"
    )
    op_a1_mascot = OrderPosition.objects.create(
        order=order_a1,
        item=item_mascot,
        variation=None,
        price=Decimal("10")
    )
    op_a2_ticket = OrderPosition.objects.create(
        order=order_a2,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name="A2"
    )
    op_a3_ticket = OrderPosition.objects.create(
        order=order_a3,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name="a4",  # a3 attendee is a4
        attendee_email="a3company@dummy.test"
    )

    # checkin
    Checkin.objects.create(position=op_a1_ticket, datetime=now() + timedelta(minutes=1))
    Checkin.objects.create(position=op_a3_ticket)

    return event, user, orga, [item_ticket, item_mascot], [order_pending, order_a1, order_a2, order_a3], \
        [op_pending_ticket, op_a1_ticket, op_a1_mascot, op_a2_ticket, op_a3_ticket]


@pytest.mark.django_db
@pytest.mark.parametrize("order_key, expected", [
    ('', ['A1Ticket', 'A1Mascot', 'A2Ticket', 'A3Ticket']),
    ('-code', ['A3Ticket', 'A2Ticket', 'A1Ticket', 'A1Mascot']),
    ('code', ['A1Ticket', 'A1Mascot', 'A2Ticket', 'A3Ticket']),
    ('-email', ['A3Ticket', 'A2Ticket', 'A1Ticket', 'A1Mascot']),
    ('email', ['A1Ticket', 'A1Mascot', 'A2Ticket', 'A3Ticket']),
    ('-status', ['A3Ticket', 'A1Ticket', 'A1Mascot', 'A2Ticket']),
    ('status', ['A1Mascot', 'A2Ticket', 'A1Ticket', 'A3Ticket']),
    ('-timestamp', ['A1Ticket', 'A3Ticket', 'A1Mascot', 'A2Ticket']),  # A1 checkin date > A3 checkin date
    ('timestamp', ['A1Mascot', 'A2Ticket', 'A3Ticket', 'A1Ticket']),
    ('-name', ['A3Ticket', 'A2Ticket', 'A1Ticket', 'A1Mascot']),
    ('name', ['A1Mascot', 'A1Ticket', 'A2Ticket', 'A3Ticket']),  # mascot doesn't include attendee name
    ('-item', ['A1Ticket', 'A2Ticket', 'A3Ticket', 'A1Mascot']),
    ('item', ['A1Mascot', 'A1Ticket', 'A2Ticket', 'A3Ticket']),
])
def test_checkins_list_ordering(client, checkin_list_env, order_key, expected):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/checkins/?ordering=' + order_key)
    qs = response.context['entries']
    item_keys = [q.order.code + str(q.item.name) for q in qs]
    assert item_keys == expected


@pytest.mark.django_db
@pytest.mark.parametrize("query, expected", [
    ('status=&item=&user=', ['A1Ticket', 'A1Mascot', 'A2Ticket', 'A3Ticket']),
    ('status=1&item=&user=', ['A1Ticket', 'A3Ticket']),
    ('status=0&item=&user=', ['A1Mascot', 'A2Ticket']),
    ('status=&item=&user=a3dummy', ['A3Ticket']),  # match order email
    ('status=&item=&user=a3dummy', ['A3Ticket']),  # match order email,
    ('status=&item=&user=a4', ['A3Ticket']),  # match attendee name
    ('status=&item=&user=a3company', ['A3Ticket']),  # match attendee email
    ('status=1&item=&user=a3company', ['A3Ticket']),
])
def test_checkins_list_filter(client, checkin_list_env, query, expected):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/checkins/?' + query)
    qs = response.context['entries']
    item_keys = [q.order.code + str(q.item.name) for q in qs]
    print([str(item.name) + '-' + str(item.id) for item in Item.objects.all()])
    assert item_keys == expected


@pytest.mark.django_db
def test_checkins_item_filter(client, checkin_list_env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    for item in checkin_list_env[3]:
        response = client.get('/control/event/dummy/dummy/checkins/?item=' + str(item.id))
        assert all(i.item.id == item.id for i in response.context['entries'])


@pytest.mark.django_db
@pytest.mark.parametrize("query, expected", [
    ('status=&item=&user=&ordering=', ['A1Ticket', 'A1Mascot', 'A2Ticket', 'A3Ticket']),
    ('status=1&item=&user=&ordering=timestamp', ['A3Ticket', 'A1Ticket']),
    ('status=0&item=&user=&ordering=-name', ['A2Ticket', 'A1Mascot']),
])
def test_checkins_list_mixed(client, checkin_list_env, query, expected):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/checkins/?' + query)
    qs = response.context['entries']
    item_keys = [q.order.code + str(q.item.name) for q in qs]
    assert item_keys == expected


@pytest.mark.django_db
def test_manual_checkins(client, checkin_list_env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    assert not checkin_list_env[5][3].checkins.exists()
    client.post('/control/event/dummy/dummy/checkins/', {
        'checkin': [checkin_list_env[5][3].pk]
    })
    assert checkin_list_env[5][3].checkins.exists()
    assert LogEntry.objects.filter(
        action_type='pretix.control.views.checkin', object_id=checkin_list_env[5][3].order.pk
    ).exists()


@pytest.fixture
def checkin_list_with_addon_env():
    # permission
    orga = Organizer.objects.create(name='Dummy', slug='dummy')
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    team = Team.objects.create(organizer=orga, can_view_orders=True, can_change_orders=True)
    team.members.add(user)

    # event
    event = Event.objects.create(
        organizer=orga, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,tests.testdummy'
    )
    event.settings.set('ticketoutput_testdummy__enabled', True)
    event.settings.set('attendee_names_asked', True)
    event.settings.set('locales', ['en', 'de'])
    team.limit_events.add(event)

    # item
    cat_adm = ItemCategory.objects.create(event=event, name="Admission")
    cat_workshop = ItemCategory.objects.create(event=event, name="Admission", is_addon=True)
    item_ticket = Item.objects.create(event=event, name="Ticket", default_price=23, admission=True, category=cat_adm)
    item_workshop = Item.objects.create(event=event, name="Workshop", default_price=10, admission=False,
                                        category=cat_workshop)
    ItemAddOn.objects.create(base_item=item_ticket, addon_category=cat_workshop, min_count=0, max_count=2)

    # order
    order_pending = Order.objects.create(
        code='PENDING', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, payment_provider='banktransfer', locale='en'
    )
    order_a1 = Order.objects.create(
        code='A1', event=event, email='a1dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=33, payment_provider='banktransfer', locale='en'
    )
    order_a2 = Order.objects.create(
        code='A2', event=event, email='a2dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, payment_provider='banktransfer', locale='en'
    )

    # order position
    op_pending_ticket = OrderPosition.objects.create(
        order=order_pending,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name="Pending"
    )
    op_a1_ticket = OrderPosition.objects.create(
        order=order_a1,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name="A1"
    )
    op_a1_workshop = OrderPosition.objects.create(
        order=order_a1,
        item=item_workshop,
        variation=None,
        price=Decimal("10"),
        addon_to=op_a1_ticket
    )
    op_a2_ticket = OrderPosition.objects.create(
        order=order_a2,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name="A2"
    )

    # checkin
    Checkin.objects.create(position=op_a1_ticket, datetime=now() + timedelta(minutes=1))

    return event, user, orga, [item_ticket, item_workshop], [order_pending, order_a1, order_a2], \
        [op_pending_ticket, op_a1_ticket, op_a1_workshop, op_a2_ticket]


@pytest.mark.django_db
def test_checkins_attendee_name_from_addon_available(client, checkin_list_with_addon_env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/checkins/')
    qs = response.context['entries']
    item_keys = [q.order.code + str(q.item.name) +
                 (str(q.addon_to.attendee_name) if q.addon_to is not None else str(q.attendee_name)) for q in qs]
    assert item_keys == ['A1TicketA1', 'A1WorkshopA1', 'A2TicketA2']  # A1Workshop<name> comes from addon_to position


@pytest.mark.django_db
def test_checkins_with_noadm_option(client, checkin_list_with_addon_env):
    checkin_list_with_addon_env[0].settings.ticket_download_nonadm = False
    checkin_list_with_addon_env[0].save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/checkins/')
    qs = response.context['entries']
    item_keys = [q.order.code + str(q.item.name) +
                 (str(q.addon_to.attendee_name) if q.addon_to is not None else str(q.attendee_name)) for q in qs]
    assert item_keys == ['A1TicketA1', 'A2TicketA2']
