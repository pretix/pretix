#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import datetime
from decimal import Decimal

from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.base import SoupTest

from pretix.base.models import (
    Event, InvoiceAddress, Item, Order, OrderPayment, OrderPosition, Organizer,
    Team, User,
)


class OrderSearchTest(SoupTest):
    @scopes_disabled()
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
        InvoiceAddress.objects.create(order=o1, company="Test Ltd.", name_parts={'full_name': "Peter Miller", "_scheme": "full"})
        ticket1 = Item.objects.create(event=self.event1, name='Early-bird ticket',
                                      category=None, default_price=23,
                                      admission=True)
        OrderPosition.objects.create(
            order=o1,
            item=ticket1,
            variation=None,
            price=Decimal("14"),
            attendee_name_parts={'full_name': "Peter", "_scheme": "full"},
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
            attendee_name_parts={'full_name': "Mark", "_scheme": "full"}
        )

        self.team = Team.objects.create(organizer=self.orga1, can_view_orders=True)
        self.team.members.add(self.user)
        self.team.limit_events.add(self.event1)

        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_team_limit_event(self):
        resp = self.client.get('/control/search/orders/').content.decode()
        assert 'FO1' in resp
        assert 'FO2' not in resp

    def test_team_limit_event_wrong_permission(self):
        self.team.can_view_orders = False
        self.team.save()
        resp = self.client.get('/control/search/orders/').content.decode()
        assert 'FO1' not in resp
        assert 'FO2' not in resp

    def test_team_all_events(self):
        self.team.all_events = True
        self.team.save()
        resp = self.client.get('/control/search/orders/').content.decode()
        assert 'FO1' in resp
        assert 'FO2' in resp

    def test_team_all_events_wrong_permission(self):
        self.team.all_events = True
        self.team.can_view_orders = False
        self.team.save()
        resp = self.client.get('/control/search/orders/').content.decode()
        assert 'FO1' not in resp
        assert 'FO2' not in resp

    def test_team_none(self):
        self.team.members.clear()
        resp = self.client.get('/control/search/orders/').content.decode()
        assert 'FO1' not in resp
        assert 'FO2' not in resp

    def test_superuser(self):
        self.user.is_staff = True
        self.user.staffsession_set.create(date_start=now(), session_key=self.client.session.session_key)
        self.user.save()
        self.team.members.clear()
        resp = self.client.get('/control/search/orders/').content.decode()
        assert 'FO1' in resp
        assert 'FO2' in resp

    def test_filter_email(self):
        resp = self.client.get('/control/search/orders/?query=dummy1@dummy').content.decode()
        assert 'FO1' in resp
        resp = self.client.get('/control/search/orders/?query=dummynope').content.decode()
        assert 'FO1' not in resp

    def test_filter_attendee_name(self):
        resp = self.client.get('/control/search/orders/?query=Pete').content.decode()
        assert 'FO1' in resp
        resp = self.client.get('/control/search/orders/?query=Mark').content.decode()
        assert 'FO1' not in resp

    def test_filter_attendee_email(self):
        resp = self.client.get('/control/search/orders/?query=att.com').content.decode()
        assert 'FO1' in resp
        resp = self.client.get('/control/search/orders/?query=nope.com').content.decode()
        assert 'FO1' not in resp

    def test_filter_invoice_address(self):
        resp = self.client.get('/control/search/orders/?query=Ltd').content.decode()
        assert 'FO1' in resp
        resp = self.client.get('/control/search/orders/?query=Miller').content.decode()
        assert 'FO1' in resp

    def test_filter_code(self):
        resp = self.client.get('/control/search/orders/?query=FO1').content.decode()
        assert '30C3-FO1' in resp
        resp = self.client.get('/control/search/orders/?query=30c3-FO1').content.decode()
        assert '30C3-FO1' in resp
        resp = self.client.get('/control/search/orders/?query=30C3-fO1A').content.decode()
        assert '30C3-FO1' in resp
        resp = self.client.get('/control/search/orders/?query=30C3-fo14').content.decode()
        assert '30C3-FO1' in resp
        resp = self.client.get('/control/search/orders/?query=31c3-FO1').content.decode()
        assert '30C3-FO1' not in resp
        resp = self.client.get('/control/search/orders/?query=FO2').content.decode()
        assert '30C3-FO1' not in resp


class PaymentSearchTest(SoupTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='NoOrga', slug='no')
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
        InvoiceAddress.objects.create(order=o1, company="Test Ltd.", name_parts={'full_name': "Peter Miller", "_scheme": "full"})
        ticket1 = Item.objects.create(event=self.event1, name='Early-bird ticket',
                                      category=None, default_price=23,
                                      admission=True)
        OrderPosition.objects.create(
            order=o1,
            item=ticket1,
            variation=None,
            price=Decimal("14"),
            attendee_name_parts={'full_name': "Peter", "_scheme": "full"},
            attendee_email="att@att.com"
        )
        OrderPayment.objects.create(
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            amount=Decimal("14"),
            order=o1,
            provider="giftcard",
            info="{test payment order 1}"
        )
        OrderPayment.objects.create(
            state=OrderPayment.PAYMENT_STATE_REFUNDED,
            amount=Decimal("14"),
            order=o1,
            provider="manual",
            info="{refunded payment}"
        )
        OrderPayment.objects.create(
            state=OrderPayment.PAYMENT_STATE_CANCELED,
            amount=Decimal("14"),
            order=o1,
            provider="manual",
            info="{canceled payment}"
        )
        OrderPayment.objects.create(
            state=OrderPayment.PAYMENT_STATE_FAILED,
            amount=Decimal("14"),
            order=o1,
            provider="manual",
            info="{failed payment}"
        )
        OrderPayment.objects.create(
            state=OrderPayment.PAYMENT_STATE_PENDING,
            amount=Decimal("14"),
            order=o1,
            provider="manual",
            info="{pending payment}"
        )

        o2 = Order.objects.create(
            code='FO2', event=self.event2, email='dummy2@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now() + datetime.timedelta(days=10),
            total=15, locale='en'
        )
        ticket2 = Item.objects.create(event=self.event1, name='Early-bird ticket',
                                      category=None, default_price=23,
                                      admission=True)
        OrderPosition.objects.create(
            order=o2,
            item=ticket2,
            variation=None,
            price=Decimal("15"),
            attendee_name_parts={'full_name': "Mark", "_scheme": "full"}
        )
        OrderPayment.objects.create(
            state=OrderPayment.PAYMENT_STATE_CREATED,
            amount=Decimal("15"),
            order=o2,
            provider="manual",
            info="{test payment order 2}"
        )

        self.team = Team.objects.create(organizer=self.orga1, can_view_orders=True)
        self.team2 = Team.objects.create(organizer=self.orga2, can_view_orders=True)
        self.team.members.add(self.user)
        self.team.limit_events.add(self.event1)

        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_team_limit_event(self):
        resp = self.client.get('/control/search/payments/').content.decode()
        assert 'FO1' in resp
        assert 'FO2' not in resp

    def test_team_limit_event_wrong_permission(self):
        self.team.can_view_orders = False
        self.team.save()
        resp = self.client.get('/control/search/payments/').content.decode()
        assert 'FO1' not in resp
        assert 'FO2' not in resp

    def test_team_all_events(self):
        self.team.all_events = True
        self.team.save()
        resp = self.client.get('/control/search/payments/').content.decode()
        assert 'FO1' in resp
        assert 'FO2' in resp

    def test_team_all_events_wrong_permission(self):
        self.team.all_events = True
        self.team.can_view_orders = False
        self.team.save()
        resp = self.client.get('/control/search/payments/').content.decode()
        assert 'FO1' not in resp
        assert 'FO2' not in resp

    def test_team_none(self):
        self.team.members.clear()
        resp = self.client.get('/control/search/payments/').content.decode()
        assert 'FO1' not in resp
        assert 'FO2' not in resp

    def test_superuser(self):
        self.user.is_staff = True
        self.user.staffsession_set.create(date_start=now(), session_key=self.client.session.session_key)
        self.user.save()
        self.team.members.clear()
        resp = self.client.get('/control/search/payments/').content.decode()
        assert 'FO1' in resp
        assert 'FO2' in resp

    def test_filter_email(self):
        resp = self.client.get('/control/search/payments/?query=dummy1@dummy').content.decode()
        assert 'FO1' in resp
        resp = self.client.get('/control/search/payments/?query=dummynope').content.decode()
        assert 'FO1' not in resp

    def test_filter_invoice_name(self):
        resp = self.client.get('/control/search/payments/?query=Pete').content.decode()
        assert 'FO1' in resp
        resp = self.client.get('/control/search/payments/?query=Mark').content.decode()
        assert 'FO1' not in resp

    def test_filter_invoice_address(self):
        resp = self.client.get('/control/search/payments/?query=Ltd').content.decode()
        assert 'FO1' in resp
        resp = self.client.get('/control/search/payments/?query=Miller').content.decode()
        assert 'FO1' in resp
        resp = self.client.get('/control/search/payments/?query=Mark').content.decode()
        assert 'FO1' not in resp

    def test_filter_code(self):
        resp = self.client.get('/control/search/payments/?query=FO1').content.decode()
        assert '30C3-FO1' in resp
        resp = self.client.get('/control/search/payments/?query=30c3-FO1').content.decode()
        assert '30C3-FO1' in resp
        resp = self.client.get('/control/search/payments/?query=30C3-fO1A').content.decode()
        assert '30C3-FO1' in resp
        resp = self.client.get('/control/search/payments/?query=30C3-fo14').content.decode()
        assert '30C3-FO1' in resp
        resp = self.client.get('/control/search/payments/?query=31c3-FO1').content.decode()
        assert '30C3-FO1' not in resp
        resp = self.client.get('/control/search/payments/?query=FO2').content.decode()
        assert '30C3-FO1' not in resp

    def test_filter_amount(self):
        self.team.all_events = True
        self.team.save()
        resp = self.client.get('/control/search/payments/?amount=14').content.decode()
        assert 'FO1' in resp
        assert 'FO2' not in resp
        resp = self.client.get('/control/search/payments/?amount=15.00').content.decode()
        assert 'FO1' not in resp
        assert 'FO2' in resp

    def test_filter_event(self):
        self.team.all_events = True
        self.team.save()
        event_id = str(self.event1.pk)
        resp = self.client.get('/control/search/payments/?event=' + event_id).content.decode()
        assert "FO1" in resp
        assert "FO2" not in resp

    def test_filter_organizer(self):
        self.team2.members.add(self.user)
        self.user.save()

        b = str(self.orga1.pk)
        resp = self.client.get('/control/search/payments/?organizer=' + b).content.decode()
        assert "FO1" in resp

        b = str(self.orga2.pk)
        resp = self.client.get('/control/search/payments/?organizer=' + b).content.decode()
        assert "FO1" not in resp

    def test_filter_state(self):
        self.user.is_staff = True
        self.user.staffsession_set.create(date_start=now(), session_key=self.client.session.session_key)
        self.user.save()

        confirmed = OrderPayment.PAYMENT_STATE_CONFIRMED
        resp = self.client.get('/control/search/payments/?state=' + confirmed).content.decode()
        assert "FO1A-P-1" in resp
        assert "FO1A-P-2" not in resp
        assert "FO1A-P-3" not in resp
        assert "FO1A-P-4" not in resp
        assert "FO1A-P-5" not in resp
        assert "FO1A-P-6" not in resp

    def test_filter_provider(self):
        resp = self.client.get('/control/search/payments/?provider=giftcard').content.decode()
        assert "FO1A-P-1" in resp
        assert "FO1A-P-2" not in resp
        assert "FO1A-P-3" not in resp
        assert "FO1A-P-4" not in resp
        assert "FO1A-P-5" not in resp
        assert "FO1A-P-6" not in resp
