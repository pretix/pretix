import datetime
from decimal import Decimal

from django.utils.timezone import now
from tests.base import SoupTest

from pretix.base.models import (
    Event, InvoiceAddress, Item, Order, OrderPosition, Organizer, Team, User,
)


class OrderSearchTest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.banktransfer,tests.testdummy'
        )
        self.event2 = Event.objects.create(
            organizer=self.orga1, name='31C3', slug='31c3',
            date_from=datetime.datetime(2014, 12, 26, tzinfo=datetime.timezone.utc),
        )

        o1 = Order.objects.create(
            code='FO1A', event=self.event1, email='dummy1@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now() + datetime.timedelta(days=10),
            total=14, locale='en'
        )
        InvoiceAddress.objects.create(order=o1, company="Test Ltd.", name_parts={'full_name': "Peter Miller"})
        ticket1 = Item.objects.create(event=self.event1, name='Early-bird ticket',
                                      category=None, default_price=23,
                                      admission=True)
        OrderPosition.objects.create(
            order=o1,
            item=ticket1,
            variation=None,
            price=Decimal("14"),
            attendee_name_parts={'full_name': "Peter"},
            attendee_email="att@att.com"
        )

        o2 = Order.objects.create(
            code='FO2', event=self.event2, email='dummy2@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now() + datetime.timedelta(days=10),
            total=14, locale='en'
        )
        ticket2 = Item.objects.create(event=self.event1, name='Early-bird ticket',
                                      category=None, default_price=23,
                                      admission=True)
        OrderPosition.objects.create(
            order=o2,
            item=ticket2,
            variation=None,
            price=Decimal("14"),
            attendee_name_parts={'full_name': "Mark"}
        )

        self.team = Team.objects.create(organizer=self.orga1, can_view_orders=True)
        self.team.members.add(self.user)
        self.team.limit_events.add(self.event1)

        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_team_limit_event(self):
        resp = self.client.get('/control/search/orders/').rendered_content
        assert 'FO1' in resp
        assert 'FO2' not in resp

    def test_team_limit_event_wrong_permission(self):
        self.team.can_view_orders = False
        self.team.save()
        resp = self.client.get('/control/search/orders/').rendered_content
        assert 'FO1' not in resp
        assert 'FO2' not in resp

    def test_team_all_events(self):
        self.team.all_events = True
        self.team.save()
        resp = self.client.get('/control/search/orders/').rendered_content
        assert 'FO1' in resp
        assert 'FO2' in resp

    def test_team_all_events_wrong_permission(self):
        self.team.all_events = True
        self.team.can_view_orders = False
        self.team.save()
        resp = self.client.get('/control/search/orders/').rendered_content
        assert 'FO1' not in resp
        assert 'FO2' not in resp

    def test_team_none(self):
        self.team.members.clear()
        resp = self.client.get('/control/search/orders/').rendered_content
        assert 'FO1' not in resp
        assert 'FO2' not in resp

    def test_superuser(self):
        self.user.is_staff = True
        self.user.staffsession_set.create(date_start=now(), session_key=self.client.session.session_key)
        self.user.save()
        self.team.members.clear()
        resp = self.client.get('/control/search/orders/').rendered_content
        assert 'FO1' in resp
        assert 'FO2' in resp

    def test_filter_email(self):
        resp = self.client.get('/control/search/orders/?query=dummy1@dummy').rendered_content
        assert 'FO1' in resp
        resp = self.client.get('/control/search/orders/?query=dummynope').rendered_content
        assert 'FO1' not in resp

    def test_filter_attendee_name(self):
        resp = self.client.get('/control/search/orders/?query=Pete').rendered_content
        assert 'FO1' in resp
        resp = self.client.get('/control/search/orders/?query=Mark').rendered_content
        assert 'FO1' not in resp

    def test_filter_attendee_email(self):
        resp = self.client.get('/control/search/orders/?query=att.com').rendered_content
        assert 'FO1' in resp
        resp = self.client.get('/control/search/orders/?query=nope.com').rendered_content
        assert 'FO1' not in resp

    def test_filter_invoice_address(self):
        resp = self.client.get('/control/search/orders/?query=Ltd').rendered_content
        assert 'FO1' in resp
        resp = self.client.get('/control/search/orders/?query=Miller').rendered_content
        assert 'FO1' in resp

    def test_filter_code(self):
        resp = self.client.get('/control/search/orders/?query=FO1').rendered_content
        assert '30C3-FO1' in resp
        resp = self.client.get('/control/search/orders/?query=30c3-FO1').rendered_content
        assert '30C3-FO1' in resp
        resp = self.client.get('/control/search/orders/?query=30C3-fO1A').rendered_content
        assert '30C3-FO1' in resp
        resp = self.client.get('/control/search/orders/?query=30C3-fo14').rendered_content
        assert '30C3-FO1' in resp
        resp = self.client.get('/control/search/orders/?query=31c3-FO1').rendered_content
        assert '30C3-FO1' not in resp
        resp = self.client.get('/control/search/orders/?query=FO2').rendered_content
        assert '30C3-FO1' not in resp
