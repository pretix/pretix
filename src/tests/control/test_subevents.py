import datetime
from decimal import Decimal

from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.base import SoupTest, extract_form_fields

from pretix.base.models import (
    Event, Order, OrderPosition, Organizer, SubEvent, Team, User,
)
from pretix.base.models.items import SubEventItem


class SubEventsTest(SoupTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.banktransfer,tests.testdummy',
            has_subevents=True
        )

        t = Team.objects.create(organizer=self.orga1, can_create_events=True, can_change_event_settings=True,
                                can_change_items=True)
        t.members.add(self.user)
        t.limit_events.add(self.event1)
        self.ticket = self.event1.items.create(name='Early-bird ticket',
                                               category=None, default_price=23,
                                               admission=True)

        self.client.login(email='dummy@dummy.dummy', password='dummy')

        self.subevent1 = self.event1.subevents.create(name='SE1', date_from=now())
        self.subevent2 = self.event1.subevents.create(name='SE2', date_from=now())

    def test_list(self):
        doc = self.get_doc('/control/event/ccc/30c3/subevents/')
        tabletext = doc.select("#page-wrapper .table")[0].text
        self.assertIn("SE1", tabletext)

    def test_create(self):
        doc = self.get_doc('/control/event/ccc/30c3/subevents/add')
        assert doc.select("input[name=quotas-TOTAL_FORMS]")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/add', {
            'name_0': 'SE2',
            'active': 'on',
            'date_from_0': '2017-07-01',
            'date_from_1': '10:00:00',
            'date_to_0': '2017-07-01',
            'date_to_1': '12:00:00',
            'location_0': 'Hamburg',
            'presale_start_0': '2017-06-20',
            'presale_start_1': '10:00:00',
            'checkinlist_set-TOTAL_FORMS': '1',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
            'checkinlist_set-0-name': 'Default',
            'checkinlist_set-0-all_products': 'on',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'item-%d-price' % self.ticket.pk: '12'
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            se = self.event1.subevents.first()
            assert str(se.name) == "SE2"
            assert se.active
            assert se.date_from.isoformat() == "2017-07-01T10:00:00+00:00"
            assert se.date_to.isoformat() == "2017-07-01T12:00:00+00:00"
            assert str(se.location) == "Hamburg"
            assert se.presale_start.isoformat() == "2017-06-20T10:00:00+00:00"
            assert not se.presale_end
            assert se.quotas.count() == 1
            q = se.quotas.last()
            assert q.name == "Q1"
            assert q.size == 50
            assert list(q.items.all()) == [self.ticket]
            sei = SubEventItem.objects.get(subevent=se, item=self.ticket)
            assert sei.price == 12
            assert se.checkinlist_set.count() == 1

    def test_modify(self):
        doc = self.get_doc('/control/event/ccc/30c3/subevents/%d/' % self.subevent1.pk)
        assert doc.select("input[name=quotas-TOTAL_FORMS]")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/%d/' % self.subevent1.pk, {
            'name_0': 'SE2',
            'active': 'on',
            'date_from_0': '2017-07-01',
            'date_from_1': '10:00:00',
            'date_to_0': '2017-07-01',
            'date_to_1': '12:00:00',
            'location_0': 'Hamburg',
            'presale_start_0': '2017-06-20',
            'presale_start_1': '10:00:00',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'checkinlist_set-TOTAL_FORMS': '1',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
            'checkinlist_set-0-name': 'Default',
            'checkinlist_set-0-all_products': 'on',
            'item-%d-price' % self.ticket.pk: '12'
        })
        assert doc.select(".alert-success")
        self.subevent1.refresh_from_db()
        se = self.subevent1
        assert str(se.name) == "SE2"
        assert se.active
        assert se.date_from.isoformat() == "2017-07-01T10:00:00+00:00"
        assert se.date_to.isoformat() == "2017-07-01T12:00:00+00:00"
        assert str(se.location) == "Hamburg"
        assert se.presale_start.isoformat() == "2017-06-20T10:00:00+00:00"
        assert not se.presale_end
        with scopes_disabled():
            assert se.quotas.count() == 1
            q = se.quotas.last()
            assert q.name == "Q1"
            assert q.size == 50
            assert list(q.items.all()) == [self.ticket]
            sei = SubEventItem.objects.get(subevent=se, item=self.ticket)
            assert sei.price == 12
            assert se.checkinlist_set.count() == 1

    def test_delete(self):
        doc = self.get_doc('/control/event/ccc/30c3/subevents/%d/delete' % self.subevent1.pk)
        assert doc.select("button")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/%d/delete' % self.subevent1.pk, {})
        assert doc.select(".alert-success")
        # deleting the second event
        doc = self.post_doc('/control/event/ccc/30c3/subevents/%d/delete' % self.subevent2.pk, {})
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert not SubEvent.objects.filter(pk=self.subevent2.pk).exists()
            assert not SubEvent.objects.filter(pk=self.subevent1.pk).exists()

    def test_delete_with_orders(self):
        with scopes_disabled():
            o = Order.objects.create(
                code='FOO', event=self.event1, email='dummy@dummy.test',
                status=Order.STATUS_PENDING,
                datetime=now(), expires=now() + datetime.timedelta(days=10),
                total=14, locale='en'
            )
            OrderPosition.objects.create(
                order=o,
                item=self.ticket,
                subevent=self.subevent1,
                price=Decimal("14"),
            )
        doc = self.get_doc('/control/event/ccc/30c3/subevents/%d/delete' % self.subevent1.pk, follow=True)
        assert doc.select(".alert-danger")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/%d/delete' % self.subevent1.pk, {}, follow=True)
        assert doc.select(".alert-danger")
        with scopes_disabled():
            assert self.event1.subevents.filter(pk=self.subevent1.pk).exists()

    def test_create_bulk(self):
        with scopes_disabled():
            self.event1.subevents.all().delete()
        self.event1.settings.timezone = 'Europe/Berlin'

        doc = self.get_doc('/control/event/ccc/30c3/subevents/bulk_add')
        assert doc.select("input[name=rruleformset-TOTAL_FORMS]")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_add', {
            'rruleformset-TOTAL_FORMS': '1',
            'rruleformset-INITIAL_FORMS': '0',
            'rruleformset-MIN_NUM_FORMS': '0',
            'rruleformset-MAX_NUM_FORMS': '1000',
            'rruleformset-0-interval': '1',
            'rruleformset-0-freq': 'yearly',
            'rruleformset-0-dtstart': '2018-04-03',
            'rruleformset-0-yearly_same': 'on',
            'rruleformset-0-yearly_bysetpos': '1',
            'rruleformset-0-yearly_byweekday': 'MO',
            'rruleformset-0-yearly_bymonth': '1',
            'rruleformset-0-monthly_same': 'on',
            'rruleformset-0-monthly_bysetpos': '1',
            'rruleformset-0-monthly_byweekday': 'MO',
            'rruleformset-0-end': 'count',
            'rruleformset-0-count': '10',
            'rruleformset-0-until': '2019-04-03',
            'timeformset-TOTAL_FORMS': '1',
            'timeformset-INITIAL_FORMS': '0',
            'timeformset-MIN_NUM_FORMS': '1',
            'timeformset-MAX_NUM_FORMS': '1000',
            'timeformset-0-time_from': '13:29:31',
            'timeformset-0-time_to': '15:29:31',
            'name_0': 'Foo',
            'active': 'on',
            'location_0': 'Loc',
            'time_admission': '',
            'frontpage_text_0': '',
            'rel_presale_start_0': 'unset',
            'rel_presale_start_1': '',
            'rel_presale_start_2': '1',
            'rel_presale_start_3': 'date_from',
            'rel_presale_start_4': '',
            'rel_presale_end_1': '',
            'rel_presale_end_0': 'relative',
            'rel_presale_end_2': '1',
            'rel_presale_end_3': 'date_from',
            'rel_presale_end_4': '13:29:31',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-id': '',
            'quotas-0-name': 'Bar',
            'quotas-0-size': '12',
            'quotas-0-itemvars': str(self.ticket.pk),
            'item-%d-price' % self.ticket.pk: '16',
            'checkinlist_set-TOTAL_FORMS': '1',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
            'checkinlist_set-0-id': '',
            'checkinlist_set-0-name': 'Foo',
            'checkinlist_set-0-limit_products': str(self.ticket.pk),
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            ses = list(self.event1.subevents.order_by('date_from'))
        assert len(ses) == 10

        assert str(ses[0].name) == "Foo"
        assert ses[0].date_from.isoformat() == "2018-04-03T11:29:31+00:00"
        assert ses[0].date_to.isoformat() == "2018-04-03T13:29:31+00:00"
        assert not ses[0].presale_start
        assert ses[0].presale_end.isoformat() == "2018-04-02T11:29:31+00:00"
        with scopes_disabled():
            assert ses[0].quotas.count() == 1
            assert list(ses[0].quotas.first().items.all()) == [self.ticket]
            assert SubEventItem.objects.get(subevent=ses[0], item=self.ticket).price == 16
            assert ses[0].checkinlist_set.count() == 1

        assert str(ses[1].name) == "Foo"
        assert ses[1].date_from.isoformat() == "2019-04-03T11:29:31+00:00"
        assert ses[1].date_to.isoformat() == "2019-04-03T13:29:31+00:00"
        assert not ses[1].presale_start
        assert ses[1].presale_end.isoformat() == "2019-04-02T11:29:31+00:00"
        with scopes_disabled():
            assert ses[1].quotas.count() == 1
            assert list(ses[1].quotas.first().items.all()) == [self.ticket]
            assert SubEventItem.objects.get(subevent=ses[0], item=self.ticket).price == 16
            assert ses[1].checkinlist_set.count() == 1

        assert ses[-1].date_from.isoformat() == "2027-04-03T11:29:31+00:00"

    def test_create_bulk_daily_interval(self):
        with scopes_disabled():
            self.event1.subevents.all().delete()
        self.event1.settings.timezone = 'Europe/Berlin'

        doc = self.get_doc('/control/event/ccc/30c3/subevents/bulk_add')
        assert doc.select("input[name=rruleformset-TOTAL_FORMS]")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_add', {
            'rruleformset-TOTAL_FORMS': '1',
            'rruleformset-INITIAL_FORMS': '0',
            'rruleformset-MIN_NUM_FORMS': '0',
            'rruleformset-MAX_NUM_FORMS': '1000',
            'rruleformset-0-interval': '2',
            'rruleformset-0-freq': 'daily',
            'rruleformset-0-dtstart': '2018-04-03',
            'rruleformset-0-yearly_same': 'on',
            'rruleformset-0-yearly_bysetpos': '1',
            'rruleformset-0-yearly_byweekday': 'MO',
            'rruleformset-0-yearly_bymonth': '1',
            'rruleformset-0-monthly_same': 'on',
            'rruleformset-0-monthly_bysetpos': '1',
            'rruleformset-0-monthly_byweekday': 'MO',
            'rruleformset-0-end': 'until',
            'rruleformset-0-count': '10',
            'rruleformset-0-until': '2019-04-03',
            'timeformset-TOTAL_FORMS': '1',
            'timeformset-INITIAL_FORMS': '0',
            'timeformset-MIN_NUM_FORMS': '1',
            'timeformset-MAX_NUM_FORMS': '1000',
            'timeformset-0-time_from': '13:29:31',
            'timeformset-0-time_to': '15:29:31',
            'name_0': 'Foo',
            'active': 'on',
            'frontpage_text_0': '',
            'rel_presale_start_0': 'unset',
            'rel_presale_start_1': '',
            'rel_presale_start_2': '1',
            'rel_presale_start_3': 'date_from',
            'rel_presale_start_4': '',
            'rel_presale_end_1': '',
            'rel_presale_end_0': 'relative',
            'rel_presale_end_2': '1',
            'rel_presale_end_3': 'date_from',
            'rel_presale_end_4': '13:29:31',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '1',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'checkinlist_set-TOTAL_FORMS': '0',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            ses = list(self.event1.subevents.order_by('date_from'))
        assert len(ses) == 183

        assert ses[0].date_from.isoformat() == "2018-04-03T11:29:31+00:00"
        assert ses[110].date_from.isoformat() == "2018-11-09T12:29:31+00:00"  # DST :)
        assert ses[-1].date_from.isoformat() == "2019-04-02T11:29:31+00:00"

    def test_create_bulk_daily_interval_multiple_times(self):
        with scopes_disabled():
            self.event1.subevents.all().delete()
        self.event1.settings.timezone = 'Europe/Berlin'

        doc = self.get_doc('/control/event/ccc/30c3/subevents/bulk_add')
        assert doc.select("input[name=rruleformset-TOTAL_FORMS]")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_add', {
            'rruleformset-TOTAL_FORMS': '1',
            'rruleformset-INITIAL_FORMS': '0',
            'rruleformset-MIN_NUM_FORMS': '0',
            'rruleformset-MAX_NUM_FORMS': '1000',
            'rruleformset-0-interval': '2',
            'rruleformset-0-freq': 'daily',
            'rruleformset-0-dtstart': '2018-04-03',
            'rruleformset-0-yearly_same': 'on',
            'rruleformset-0-yearly_bysetpos': '1',
            'rruleformset-0-yearly_byweekday': 'MO',
            'rruleformset-0-yearly_bymonth': '1',
            'rruleformset-0-monthly_same': 'on',
            'rruleformset-0-monthly_bysetpos': '1',
            'rruleformset-0-monthly_byweekday': 'MO',
            'rruleformset-0-end': 'until',
            'rruleformset-0-count': '10',
            'rruleformset-0-until': '2019-04-03',
            'timeformset-TOTAL_FORMS': '2',
            'timeformset-INITIAL_FORMS': '0',
            'timeformset-MIN_NUM_FORMS': '1',
            'timeformset-MAX_NUM_FORMS': '1000',
            'timeformset-0-time_from': '13:29:31',
            'timeformset-0-time_to': '15:29:31',
            'timeformset-1-time_from': '15:29:31',
            'timeformset-1-time_to': '17:29:31',
            'name_0': 'Foo',
            'active': 'on',
            'frontpage_text_0': '',
            'rel_presale_start_0': 'unset',
            'rel_presale_start_1': '',
            'rel_presale_start_2': '1',
            'rel_presale_start_3': 'date_from',
            'rel_presale_start_4': '',
            'rel_presale_end_1': '',
            'rel_presale_end_0': 'relative',
            'rel_presale_end_2': '1',
            'rel_presale_end_3': 'date_from',
            'rel_presale_end_4': '13:29:31',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'checkinlist_set-TOTAL_FORMS': '0',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            ses = list(self.event1.subevents.order_by('date_from'))
        assert len(ses) == 183 * 2

        assert ses[0].date_from.isoformat() == "2018-04-03T11:29:31+00:00"
        assert ses[1].date_from.isoformat() == "2018-04-03T13:29:31+00:00"
        assert ses[220].date_from.isoformat() == "2018-11-09T12:29:31+00:00"  # DST :)
        assert ses[-1].date_from.isoformat() == "2019-04-02T13:29:31+00:00"

    def test_create_bulk_exclude(self):
        with scopes_disabled():
            self.event1.subevents.all().delete()
        self.event1.settings.timezone = 'Europe/Berlin'

        doc = self.get_doc('/control/event/ccc/30c3/subevents/bulk_add')
        assert doc.select("input[name=rruleformset-TOTAL_FORMS]")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_add', {
            'rruleformset-TOTAL_FORMS': '2',
            'rruleformset-INITIAL_FORMS': '0',
            'rruleformset-MIN_NUM_FORMS': '0',
            'rruleformset-MAX_NUM_FORMS': '1000',
            'rruleformset-0-interval': '1',
            'rruleformset-0-freq': 'daily',
            'rruleformset-0-dtstart': '2018-04-03',
            'rruleformset-0-yearly_same': 'on',
            'rruleformset-0-yearly_bysetpos': '1',
            'rruleformset-0-yearly_byweekday': 'MO',
            'rruleformset-0-yearly_bymonth': '1',
            'rruleformset-0-monthly_same': 'on',
            'rruleformset-0-monthly_bysetpos': '1',
            'rruleformset-0-monthly_byweekday': 'MO',
            'rruleformset-0-end': 'until',
            'rruleformset-0-count': '10',
            'rruleformset-0-until': '2019-04-03',
            'rruleformset-1-interval': '1',
            'rruleformset-1-freq': 'weekly',
            'rruleformset-1-dtstart': '2018-04-03',
            'rruleformset-1-yearly_same': 'on',
            'rruleformset-1-yearly_bysetpos': '1',
            'rruleformset-1-yearly_byweekday': 'MO',
            'rruleformset-1-yearly_bymonth': '1',
            'rruleformset-1-monthly_same': 'on',
            'rruleformset-1-monthly_bysetpos': '1',
            'rruleformset-1-monthly_byweekday': 'MO',
            'rruleformset-1-weekly_byweekday': 'MO',
            'rruleformset-1-end': 'until',
            'rruleformset-1-count': '10',
            'rruleformset-1-until': '2019-04-03',
            'rruleformset-1-exclude': 'on',
            'timeformset-TOTAL_FORMS': '1',
            'timeformset-INITIAL_FORMS': '0',
            'timeformset-MIN_NUM_FORMS': '1',
            'timeformset-MAX_NUM_FORMS': '1000',
            'timeformset-0-time_from': '13:29:31',
            'timeformset-0-time_to': '15:29:31',
            'name_0': 'Foo',
            'active': 'on',
            'frontpage_text_0': '',
            'rel_presale_start_0': 'unset',
            'rel_presale_start_1': '',
            'rel_presale_start_2': '1',
            'rel_presale_start_3': 'date_from',
            'rel_presale_start_4': '',
            'rel_presale_end_1': '',
            'rel_presale_end_0': 'relative',
            'rel_presale_end_2': '1',
            'rel_presale_end_3': 'date_from',
            'rel_presale_end_4': '13:29:31',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'checkinlist_set-TOTAL_FORMS': '0',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            ses = list(self.event1.subevents.order_by('date_from'))
        assert len(ses) == 314

        assert ses[0].date_from.isoformat() == "2018-04-03T11:29:31+00:00"
        assert ses[5].date_from.isoformat() == "2018-04-08T11:29:31+00:00"
        assert ses[6].date_from.isoformat() == "2018-04-10T11:29:31+00:00"

    def test_create_bulk_monthly_interval(self):
        with scopes_disabled():
            self.event1.subevents.all().delete()
        self.event1.settings.timezone = 'Europe/Berlin'

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_add', {
            'rruleformset-TOTAL_FORMS': '1',
            'rruleformset-INITIAL_FORMS': '0',
            'rruleformset-MIN_NUM_FORMS': '0',
            'rruleformset-MAX_NUM_FORMS': '1000',
            'rruleformset-0-interval': '1',
            'rruleformset-0-freq': 'monthly',
            'rruleformset-0-dtstart': '2018-04-03',
            'rruleformset-0-yearly_same': 'on',
            'rruleformset-0-yearly_bysetpos': '1',
            'rruleformset-0-yearly_byweekday': 'MO',
            'rruleformset-0-yearly_bymonth': '1',
            'rruleformset-0-monthly_same': 'off',
            'rruleformset-0-monthly_bysetpos': '-1',
            'rruleformset-0-monthly_byweekday': 'MO,TU,WE,TH,FR',
            'rruleformset-0-weekly_byweekday': 'TH',
            'rruleformset-0-end': 'until',
            'rruleformset-0-count': '10',
            'rruleformset-0-until': '2019-04-03',
            'timeformset-TOTAL_FORMS': '1',
            'timeformset-INITIAL_FORMS': '0',
            'timeformset-MIN_NUM_FORMS': '1',
            'timeformset-MAX_NUM_FORMS': '1000',
            'timeformset-0-time_from': '13:29:31',
            'timeformset-0-time_to': '15:29:31',
            'name_0': 'Foo',
            'active': 'on',
            'frontpage_text_0': '',
            'rel_presale_start_0': 'unset',
            'rel_presale_start_1': '',
            'rel_presale_start_2': '1',
            'rel_presale_start_3': 'date_from',
            'rel_presale_start_4': '',
            'rel_presale_end_0': 'unset',
            'rel_presale_end_1': '',
            'rel_presale_end_2': '1',
            'rel_presale_end_3': 'date_from',
            'rel_presale_end_4': '13:29:31',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'checkinlist_set-TOTAL_FORMS': '0',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            ses = list(self.event1.subevents.order_by('date_from'))
        assert len(ses) == 12

        assert ses[0].date_from.isoformat() == "2018-04-30T11:29:31+00:00"
        assert ses[1].date_from.isoformat() == "2018-05-31T11:29:31+00:00"
        assert ses[-1].date_from.isoformat() == "2019-03-29T12:29:31+00:00"

    def test_create_bulk_weekly_interval(self):
        with scopes_disabled():
            self.event1.subevents.all().delete()
        self.event1.settings.timezone = 'Europe/Berlin'

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_add', {
            'rruleformset-TOTAL_FORMS': '1',
            'rruleformset-INITIAL_FORMS': '0',
            'rruleformset-MIN_NUM_FORMS': '0',
            'rruleformset-MAX_NUM_FORMS': '1000',
            'rruleformset-0-interval': '1',
            'rruleformset-0-freq': 'weekly',
            'rruleformset-0-dtstart': '2018-04-03',
            'rruleformset-0-yearly_same': 'on',
            'rruleformset-0-yearly_bysetpos': '1',
            'rruleformset-0-yearly_byweekday': 'MO',
            'rruleformset-0-yearly_bymonth': '1',
            'rruleformset-0-monthly_same': 'on',
            'rruleformset-0-monthly_bysetpos': '-1',
            'rruleformset-0-monthly_byweekday': 'MO,TU,WE,TH,FR',
            'rruleformset-0-weekly_byweekday': 'TH',
            'rruleformset-0-end': 'until',
            'rruleformset-0-count': '10',
            'rruleformset-0-until': '2019-04-03',
            'timeformset-TOTAL_FORMS': '1',
            'timeformset-INITIAL_FORMS': '0',
            'timeformset-MIN_NUM_FORMS': '1',
            'timeformset-MAX_NUM_FORMS': '1000',
            'timeformset-0-time_from': '13:29:31',
            'timeformset-0-time_to': '15:29:31',
            'name_0': 'Foo',
            'active': 'on',
            'frontpage_text_0': '',
            'rel_presale_start_0': 'unset',
            'rel_presale_start_1': '',
            'rel_presale_start_2': '1',
            'rel_presale_start_3': 'date_from',
            'rel_presale_start_4': '',
            'rel_presale_end_0': 'unset',
            'rel_presale_end_1': '',
            'rel_presale_end_2': '1',
            'rel_presale_end_3': 'date_from',
            'rel_presale_end_4': '13:29:31',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'checkinlist_set-TOTAL_FORMS': '0',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            ses = list(self.event1.subevents.order_by('date_from'))
        assert len(ses) == 52

        assert ses[0].date_from.isoformat() == "2018-04-05T11:29:31+00:00"
        assert ses[1].date_from.isoformat() == "2018-04-12T11:29:31+00:00"
        assert ses[-1].date_from.isoformat() == "2019-03-28T12:29:31+00:00"

    def test_delete_bulk(self):
        self.subevent2.active = True
        self.subevent2.save()
        with scopes_disabled():
            o = Order.objects.create(
                code='FOO', event=self.event1, email='dummy@dummy.test',
                status=Order.STATUS_PENDING,
                datetime=now(), expires=now() + datetime.timedelta(days=10),
                total=14, locale='en'
            )
            OrderPosition.objects.create(
                order=o,
                item=self.ticket,
                subevent=self.subevent1,
                price=Decimal("14"),
            )
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_action', {
            'subevent': [str(self.subevent1.pk), str(self.subevent2.pk)],
            'action': 'delete_confirm'
        }, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert not self.event1.subevents.filter(pk=self.subevent2.pk).exists()
            assert self.event1.subevents.get(pk=self.subevent1.pk).active is False

    def test_delete_bulk_by_query(self):
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_action', {
            '__ALL': 'on',
            'filter-query': 'SE2',
            'action': 'delete_confirm'
        }, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert not self.event1.subevents.filter(pk=self.subevent2.pk).exists()
            assert self.event1.subevents.filter(pk=self.subevent1.pk).exists()

    def test_disable_bulk(self):
        self.subevent2.active = True
        self.subevent2.save()
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_action', {
            'subevent': str(self.subevent2.pk),
            'action': 'disable'
        }, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert self.event1.subevents.get(pk=self.subevent2.pk).active is False

    def test_enable_bulk(self):
        self.subevent2.active = False
        self.subevent2.save()
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_action', {
            'subevent': str(self.subevent2.pk),
            'action': 'enable'
        }, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert self.event1.subevents.get(pk=self.subevent2.pk).active is True

    def test_edit_bulk_scalar_change(self):
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert not fields.get('bulkedit-name_0')
        fields.update({
            '_bulk': ['bulkeditname'],
            'bulkedit-name_0': 'SEFOO',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert str(self.event1.subevents.get(pk=self.subevent1.pk).name) == 'SEFOO'
            assert str(self.event1.subevents.get(pk=self.subevent2.pk).name) == 'SEFOO'

    def test_edit_bulk_scalar_keep_mixed(self):
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert not fields.get('bulkedit-name_0')
        fields.update({
            '_bulk': ['bulkeditlocation'],
            'bulkedit-name_0': 'SEFOO',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert str(self.event1.subevents.get(pk=self.subevent1.pk).name) == 'SE1'
            assert str(self.event1.subevents.get(pk=self.subevent2.pk).name) == 'SE2'

    def test_edit_bulk_meta(self):
        prop1 = self.orga1.meta_properties.create(name="Prop1")
        prop2 = self.orga1.meta_properties.create(name="Prop2")
        prop2.subevent_values.create(subevent=self.subevent1, value="Bla")
        prop2.subevent_values.create(subevent=self.subevent2, value="Bla")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert not fields.get('prop-{}-value'.format(prop1.pk))
        assert fields.get('prop-{}-value'.format(prop2.pk)) == 'Bla'
        fields.update({
            '_bulk': ['prop-{}value'.format(prop1.pk), 'prop-{}value'.format(prop2.pk)],
            'prop-{}-value'.format(prop1.pk): 'Bla',
            'prop-{}-value'.format(prop2.pk): '',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert self.event1.subevents.get(pk=self.subevent1.pk).meta_data == {'Prop1': 'Bla', 'Prop2': ''}
            assert self.event1.subevents.get(pk=self.subevent2.pk).meta_data == {'Prop1': 'Bla', 'Prop2': ''}

    def test_edit_bulk_day_both_same_before(self):
        with scopes_disabled():
            self.subevent1.date_from = datetime.datetime(2013, 12, 26, 9, 0, 0, tzinfo=datetime.timezone.utc)
            self.subevent1.save()
            self.subevent2.date_from = datetime.datetime(2013, 12, 26, 11, 0, 0, tzinfo=datetime.timezone.utc)
            self.subevent2.save()

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert fields.get('bulkedit-date_from_day') == '2013-12-26'
        fields.update({
            '_bulk': ['bulkeditdate_from_day'],
            'bulkedit-date_from_day': '2013-12-27',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            self.subevent1.refresh_from_db()
            self.subevent2.refresh_from_db()
            assert self.subevent1.date_from == datetime.datetime(2013, 12, 27, 9, 0, 0, tzinfo=datetime.timezone.utc)
            assert self.subevent2.date_from == datetime.datetime(2013, 12, 27, 11, 0, 0, tzinfo=datetime.timezone.utc)

    def test_edit_bulk_day_both_different_before(self):
        with scopes_disabled():
            self.subevent1.date_from = datetime.datetime(2013, 12, 26, 9, 0, 0, tzinfo=datetime.timezone.utc)
            self.subevent1.save()
            self.subevent2.date_from = datetime.datetime(2013, 12, 27, 11, 0, 0, tzinfo=datetime.timezone.utc)
            self.subevent2.save()

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert not fields.get('bulkedit-date_from_day')
        fields.update({
            '_bulk': ['bulkeditdate_from_day'],
            'bulkedit-date_from_day': '2013-12-27',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            self.subevent1.refresh_from_db()
            self.subevent2.refresh_from_db()
            assert self.subevent1.date_from == datetime.datetime(2013, 12, 27, 9, 0, 0, tzinfo=datetime.timezone.utc)
            assert self.subevent2.date_from == datetime.datetime(2013, 12, 27, 11, 0, 0, tzinfo=datetime.timezone.utc)

    def test_edit_bulk_day_unset_before(self):
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert not fields.get('bulkedit-date_to_day')
        fields.update({
            '_bulk': ['bulkeditdate_to_day'],
            'bulkedit-date_to_day': '2013-12-27',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            self.subevent1.refresh_from_db()
            self.subevent2.refresh_from_db()
            assert self.subevent1.date_to == datetime.datetime(2013, 12, 27, 0, 0, 0, tzinfo=datetime.timezone.utc)
            assert self.subevent2.date_to == datetime.datetime(2013, 12, 27, 0, 0, 0, tzinfo=datetime.timezone.utc)

    def test_edit_bulk_day_unset(self):
        with scopes_disabled():
            self.subevent1.date_to = datetime.datetime(2013, 12, 26, 9, 0, 0, tzinfo=datetime.timezone.utc)
            self.subevent1.save()
            self.subevent2.date_to = datetime.datetime(2013, 12, 27, 11, 0, 0, tzinfo=datetime.timezone.utc)
            self.subevent2.save()

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert not fields.get('bulkedit-date_to_day')
        fields.update({
            '_bulk': ['bulkeditdate_to_day'],
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            self.subevent1.refresh_from_db()
            self.subevent2.refresh_from_db()
            assert self.subevent1.date_to is None
            assert self.subevent2.date_to is None

    def test_edit_bulk_time_both_same_before(self):
        with scopes_disabled():
            self.subevent1.date_to = datetime.datetime(2013, 12, 26, 9, 0, 0, tzinfo=datetime.timezone.utc)
            self.subevent1.save()
            self.subevent2.date_to = datetime.datetime(2013, 12, 27, 9, 0, 0, tzinfo=datetime.timezone.utc)
            self.subevent2.save()

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert fields.get('bulkedit-date_to_time') == '09:00:00'
        fields.update({
            '_bulk': ['bulkeditdate_to_time'],
            'bulkedit-date_to_time': '10:00:00',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            self.subevent1.refresh_from_db()
            self.subevent2.refresh_from_db()
            assert self.subevent1.date_to == datetime.datetime(2013, 12, 26, 10, 0, 0, tzinfo=datetime.timezone.utc)
            assert self.subevent2.date_to == datetime.datetime(2013, 12, 27, 10, 0, 0, tzinfo=datetime.timezone.utc)

    def test_edit_bulk_time_both_different_before(self):
        with scopes_disabled():
            self.subevent1.date_to = datetime.datetime(2013, 12, 26, 9, 0, 0, tzinfo=datetime.timezone.utc)
            self.subevent1.save()
            self.subevent2.date_to = datetime.datetime(2013, 12, 27, 11, 0, 0, tzinfo=datetime.timezone.utc)
            self.subevent2.save()

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert not fields.get('bulkedit-date_to_time')
        fields.update({
            '_bulk': ['bulkeditdate_to_time'],
            'bulkedit-date_to_time': '10:00:00',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            self.subevent1.refresh_from_db()
            self.subevent2.refresh_from_db()
            assert self.subevent1.date_to == datetime.datetime(2013, 12, 26, 10, 0, 0, tzinfo=datetime.timezone.utc)
            assert self.subevent2.date_to == datetime.datetime(2013, 12, 27, 10, 0, 0, tzinfo=datetime.timezone.utc)

    def test_edit_bulk_time_unset_before(self):
        with scopes_disabled():
            self.subevent1.date_from = datetime.datetime(2013, 12, 26, 9, 0, 0, tzinfo=datetime.timezone.utc)
            self.subevent1.save()
            self.subevent2.date_from = datetime.datetime(2013, 12, 27, 11, 0, 0, tzinfo=datetime.timezone.utc)
            self.subevent2.save()

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert not fields.get('bulkedit-date_to_time')
        fields.update({
            '_bulk': ['bulkeditdate_to_time'],
            'bulkedit-date_to_time': '17:00:00',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            self.subevent1.refresh_from_db()
            self.subevent2.refresh_from_db()
            assert self.subevent1.date_to == datetime.datetime(2013, 12, 26, 17, 0, 0, tzinfo=datetime.timezone.utc)
            assert self.subevent2.date_to == datetime.datetime(2013, 12, 27, 17, 0, 0, tzinfo=datetime.timezone.utc)

    def test_edit_bulk_price(self):
        sei1 = SubEventItem.objects.create(subevent=self.subevent1, item=self.ticket, price=Decimal('4.00'))
        sei2 = SubEventItem.objects.create(subevent=self.subevent2, item=self.ticket, price=Decimal('4.00'))
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert fields.get('item-{}-price'.format(self.ticket.id)) == '4.00'
        fields.update({
            '_bulk': ['item-{}price'.format(self.ticket.id)],
            'item-{}-price'.format(self.ticket.id): '5.00',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            sei1.refresh_from_db()
            sei2.refresh_from_db()
            assert sei1.price == Decimal('5.00')
            assert sei2.price == Decimal('5.00')

    def test_edit_bulk_quotas_add_and_edit(self):
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        fields.update({
            '_bulk': ['__quotas'],
            'quotas-TOTAL_FORMS': '2',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'quotas-1-name': 'Q2',
            'quotas-1-size': '25',
            'quotas-1-itemvars': str(self.ticket.pk),
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            for se in [self.subevent1, self.subevent2]:
                q = se.quotas.get(name='Q1')
                assert q.size == 50
                assert list(q.items.all()) == [self.ticket]
                q = se.quotas.get(name='Q2')
                assert q.size == 25
                assert list(q.items.all()) == [self.ticket]

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert fields['quotas-0-name'] == 'Q1'
        assert fields['quotas-1-name'] == 'Q2'
        fields.update({
            '_bulk': ['__quotas'],
            'quotas-0-size': '25',
            'quotas-1-size': '50',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            for se in [self.subevent1, self.subevent2]:
                q = se.quotas.get(name='Q1')
                assert q.size == 25
                assert list(q.items.all()) == [self.ticket]
                q = se.quotas.get(name='Q2')
                assert q.size == 50
                assert list(q.items.all()) == [self.ticket]

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        fields.update({
            '_bulk': ['__quotas'],
            'quotas-1-DELETE': 'on',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            for se in [self.subevent1, self.subevent2]:
                assert se.quotas.count() == 1

    def test_edit_bulk_quotas_mixed_replace(self):
        with scopes_disabled():
            self.subevent1.quotas.create(event=self.event1, name="Q1", size=20)
            self.subevent2.quotas.create(event=self.event1, name="Q2", size=40)
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert fields['quotas-TOTAL_FORMS'] == '0'
        fields.update({
            '_bulk': ['_invalid_'],
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert self.subevent1.quotas.get().size == 20
            assert self.subevent2.quotas.get().size == 40

        fields.update({
            '_bulk': ['__quotas'],
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '100',
            'quotas-0-itemvars': str(self.ticket.pk),
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert self.subevent1.quotas.get().size == 100
            assert self.subevent2.quotas.get().size == 100

    def test_edit_bulk_lists_add_and_edit(self):
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        fields.update({
            '_bulk': ['__checkinlists'],
            'checkinlist_set-TOTAL_FORMS': '2',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
            'checkinlist_set-0-name': 'Q1',
            'checkinlist_set-0-limit_products': str(self.ticket.pk),
            'checkinlist_set-1-name': 'Q2',
            'checkinlist_set-1-limit_products': str(self.ticket.pk),
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            for se in [self.subevent1, self.subevent2]:
                q = se.checkinlist_set.get(name='Q1')
                assert list(q.limit_products.all()) == [self.ticket]
                q = se.checkinlist_set.get(name='Q2')
                assert list(q.limit_products.all()) == [self.ticket]

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        fields.update({
            '_bulk': ['__checkinlists'],
            'checkinlist_set-1-DELETE': 'on',
        })
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            for se in [self.subevent1, self.subevent2]:
                assert se.checkinlist_set.count() == 1

    def test_edit_bulk_lists_keep_mixed(self):
        with scopes_disabled():
            self.subevent1.checkinlist_set.create(event=self.event1, name="C1")
            self.subevent2.checkinlist_set.create(event=self.event1, name="C2")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_edit', {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert 'checkinlist_set-TOTAL_FORMS' not in fields
