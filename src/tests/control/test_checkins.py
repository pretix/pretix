from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from django.utils.timezone import now

from pretix.base.models import (
    Checkin, Event, Item, ItemAddOn, ItemCategory, LogEntry, Order,
    OrderPosition, Organizer, Team, User,
)
from pretix.control.views.dashboards import checkin_widget

from ..base import SoupTest, extract_form_fields


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

    cl = event.checkin_lists.create(name="Default", all_products=True)

    event.settings.set('attendee_names_asked', True)
    event.settings.set('locales', ['en', 'de'])

    order_paid = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=33, locale='en'
    )
    OrderPosition.objects.create(
        order=order_paid,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name_parts={"full_name": "Peter"}
    )
    OrderPosition.objects.create(
        order=order_paid,
        item=item_mascot,
        variation=None,
        price=Decimal("10")
    )

    return event, user, o, order_paid, item_ticket, item_mascot, cl


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
        total=23, locale='en'
    )
    OrderPosition.objects.create(
        order=order_pending,
        item=dashboard_env[4],
        variation=None,
        price=Decimal("23"),
        attendee_name_parts={'full_name': "NotPaid"}
    )
    assert '0/2' in c[0]['content']


@pytest.mark.django_db
def test_dashboard_with_checkin(dashboard_env):
    op = OrderPosition.objects.get(
        order=dashboard_env[3],
        item=dashboard_env[4]
    )
    Checkin.objects.create(position=op, list=dashboard_env[6])
    c = checkin_widget(dashboard_env[0])
    assert '1/2' in c[0]['content']


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

    cl = event.checkin_lists.create(name="Default", all_products=True)

    # item
    item_ticket = Item.objects.create(event=event, name="Ticket", default_price=23, admission=True, position=0)
    item_mascot = Item.objects.create(event=event, name="Mascot", default_price=10, admission=False, position=1)

    # order
    order_pending = Order.objects.create(
        code='PENDING', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, locale='en'
    )
    order_a1 = Order.objects.create(
        code='A1', event=event, email='a1dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=33, locale='en'
    )
    order_a2 = Order.objects.create(
        code='A2', event=event, email='a2dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, locale='en'
    )
    order_a3 = Order.objects.create(
        code='A3', event=event, email='a3dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, locale='en'
    )

    # order position
    op_pending_ticket = OrderPosition.objects.create(
        order=order_pending,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name_parts={'full_name': "Pending"}
    )
    op_a1_ticket = OrderPosition.objects.create(
        order=order_a1,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name_parts={'full_name': "A1"}
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
        attendee_name_parts={'full_name': "A2"}
    )
    op_a3_ticket = OrderPosition.objects.create(
        order=order_a3,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name_parts={'full_name': "a4"},  # a3 attendee is a4
        attendee_email="a3company@dummy.test"
    )

    # checkin
    Checkin.objects.create(position=op_a1_ticket, datetime=now() + timedelta(minutes=1), list=cl)
    Checkin.objects.create(position=op_a3_ticket, list=cl)

    return event, user, orga, [item_ticket, item_mascot], [order_pending, order_a1, order_a2, order_a3], \
        [op_pending_ticket, op_a1_ticket, op_a1_mascot, op_a2_ticket, op_a3_ticket], cl


@pytest.mark.django_db
@pytest.mark.parametrize("order_key, expected", [
    ('', ['A1Ticket', 'A1Mascot', 'A2Ticket', 'A3Ticket']),
    ('-code', ['A3Ticket', 'A2Ticket', 'A1Ticket', 'A1Mascot']),
    ('code', ['A1Mascot', 'A1Ticket', 'A2Ticket', 'A3Ticket']),
    ('-email', ['A3Ticket', 'A2Ticket', 'A1Ticket', 'A1Mascot']),
    ('email', ['A1Mascot', 'A1Ticket', 'A2Ticket', 'A3Ticket']),
    ('-status', ['A3Ticket', 'A1Ticket', 'A2Ticket', 'A1Mascot']),
    ('status', ['A1Mascot', 'A2Ticket', 'A1Ticket', 'A3Ticket']),
    ('-timestamp', ['A1Ticket', 'A3Ticket', 'A2Ticket', 'A1Mascot']),  # A1 checkin date > A3 checkin date
    ('timestamp', ['A1Mascot', 'A2Ticket', 'A3Ticket', 'A1Ticket']),
    ('-name', ['A3Ticket', 'A2Ticket', 'A1Ticket', 'A1Mascot']),
    ('name', ['A1Mascot', 'A1Ticket', 'A2Ticket', 'A3Ticket']),  # mascot doesn't include attendee name
    ('-item', ['A3Ticket', 'A2Ticket', 'A1Ticket', 'A1Mascot']),
    ('item', ['A1Mascot', 'A1Ticket', 'A2Ticket', 'A3Ticket']),
])
def test_checkins_list_ordering(client, checkin_list_env, order_key, expected):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/checkinlists/{}/?ordering='.format(checkin_list_env[6].pk) + order_key)
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
    response = client.get('/control/event/dummy/dummy/checkinlists/{}/?'.format(checkin_list_env[6].pk) + query)
    qs = response.context['entries']
    item_keys = [q.order.code + str(q.item.name) for q in qs]
    assert item_keys == expected


@pytest.mark.django_db
def test_checkins_item_filter(client, checkin_list_env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    for item in checkin_list_env[3]:
        response = client.get('/control/event/dummy/dummy/checkinlists/{}/?item={}'.format(checkin_list_env[6].pk, item.pk))
        assert all(i.item.id == item.id for i in response.context['entries'])


@pytest.mark.django_db
@pytest.mark.parametrize("query, expected", [
    ('status=&item=&user=&ordering=', ['A1Ticket', 'A1Mascot', 'A2Ticket', 'A3Ticket']),
    ('status=1&item=&user=&ordering=timestamp', ['A3Ticket', 'A1Ticket']),
    ('status=0&item=&user=&ordering=-name', ['A2Ticket', 'A1Mascot']),
])
def test_checkins_list_mixed(client, checkin_list_env, query, expected):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/checkinlists/{}/?{}'.format(checkin_list_env[6].pk, query))
    qs = response.context['entries']
    item_keys = [q.order.code + str(q.item.name) for q in qs]
    assert item_keys == expected


@pytest.mark.django_db
def test_manual_checkins(client, checkin_list_env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    assert not checkin_list_env[5][3].checkins.exists()
    client.post('/control/event/dummy/dummy/checkinlists/{}/'.format(checkin_list_env[6].pk), {
        'checkin': [checkin_list_env[5][3].pk]
    })
    assert checkin_list_env[5][3].checkins.exists()
    assert LogEntry.objects.filter(
        action_type='pretix.event.checkin', object_id=checkin_list_env[5][3].order.pk
    ).exists()


@pytest.mark.django_db
def test_manual_checkins_revert(client, checkin_list_env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    assert not checkin_list_env[5][3].checkins.exists()
    client.post('/control/event/dummy/dummy/checkinlists/{}/'.format(checkin_list_env[6].pk), {
        'checkin': [checkin_list_env[5][3].pk]
    })
    client.post('/control/event/dummy/dummy/checkinlists/{}/'.format(checkin_list_env[6].pk), {
        'checkin': [checkin_list_env[5][3].pk],
        'revert': 'true'
    })
    assert not checkin_list_env[5][3].checkins.exists()
    assert LogEntry.objects.filter(
        action_type='pretix.event.checkin', object_id=checkin_list_env[5][3].order.pk
    ).exists()
    assert LogEntry.objects.filter(
        action_type='pretix.event.checkin.reverted', object_id=checkin_list_env[5][3].order.pk
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
    cl = event.checkin_lists.create(name="Default", all_products=True)

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
        total=23, locale='en'
    )
    order_a1 = Order.objects.create(
        code='A1', event=event, email='a1dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=33, locale='en'
    )
    order_a2 = Order.objects.create(
        code='A2', event=event, email='a2dummy@dummy.test',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23, locale='en'
    )

    # order position
    op_pending_ticket = OrderPosition.objects.create(
        order=order_pending,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name_parts={'full_name': "Pending"}
    )
    op_a1_ticket = OrderPosition.objects.create(
        order=order_a1,
        item=item_ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name_parts={'full_name': "A1"}
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
        attendee_name_parts={'full_name': "A2"}
    )

    # checkin
    Checkin.objects.create(position=op_a1_ticket, datetime=now() + timedelta(minutes=1), list=cl)

    return event, user, orga, [item_ticket, item_workshop], [order_pending, order_a1, order_a2], \
        [op_pending_ticket, op_a1_ticket, op_a1_workshop, op_a2_ticket], cl


@pytest.mark.django_db
def test_checkins_attendee_name_from_addon_available(client, checkin_list_with_addon_env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/checkinlists/{}/'.format(checkin_list_with_addon_env[6].pk))
    qs = response.context['entries']
    item_keys = [q.order.code + str(q.item.name) +
                 (str(q.addon_to.attendee_name) if q.addon_to is not None else str(q.attendee_name)) for q in qs]
    assert item_keys == ['A1TicketA1', 'A1WorkshopA1', 'A2TicketA2']  # A1Workshop<name> comes from addon_to position


class CheckinListFormTest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime(2013, 12, 26, tzinfo=timezone.utc),
        )
        t = Team.objects.create(organizer=self.orga1, can_change_event_settings=True, can_view_orders=True)
        t.members.add(self.user)
        t.limit_events.add(self.event1)
        self.client.login(email='dummy@dummy.dummy', password='dummy')
        self.item_ticket = Item.objects.create(event=self.event1, name="Ticket", default_price=23, admission=True)

    def test_create(self):
        doc = self.get_doc('/control/event/%s/%s/checkinlists/add' % (self.orga1.slug, self.event1.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['name'] = 'All'
        form_data['all_products'] = 'on'
        doc = self.post_doc('/control/event/%s/%s/checkinlists/add' % (self.orga1.slug, self.event1.slug), form_data)
        assert doc.select(".alert-success")
        self.assertIn("All", doc.select("#page-wrapper table")[0].text)
        assert self.event1.checkin_lists.get(
            name='All', all_products=True
        )

    def test_update(self):
        cl = self.event1.checkin_lists.create(name='All', all_products=True)
        doc = self.get_doc('/control/event/%s/%s/checkinlists/%s/change' % (self.orga1.slug, self.event1.slug, cl.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['all_products'] = ''
        form_data['limit_products'] = str(self.item_ticket.pk)
        doc = self.post_doc('/control/event/%s/%s/checkinlists/%s/change' % (self.orga1.slug, self.event1.slug, cl.id),
                            form_data)
        assert doc.select(".alert-success")
        cl.refresh_from_db()
        assert not cl.all_products
        assert list(cl.limit_products.all()) == [self.item_ticket]

    def test_delete(self):
        cl = self.event1.checkin_lists.create(name='All', all_products=True)
        doc = self.get_doc('/control/event/%s/%s/checkinlists/%s/delete' % (self.orga1.slug, self.event1.slug, cl.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        doc = self.post_doc('/control/event/%s/%s/checkinlists/%s/delete' % (self.orga1.slug, self.event1.slug, cl.id),
                            form_data)
        assert doc.select(".alert-success")
        self.assertNotIn("VAT", doc.select("#page-wrapper")[0].text)
        assert not self.event1.checkin_lists.exists()
