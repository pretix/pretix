import datetime
from decimal import Decimal

import pytest
import pytz
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import (
    Event, InvoiceAddress, Item, Order, OrderPosition, Organizer,
)
from pretix.plugins.checkinlists.exporters import CSVCheckinList


@pytest.fixture
def event():
    """Returns an event instance"""
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    with scope(organizer=o):
        event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
            plugins='pretix.plugins.checkinlists,tests.testdummy',
        )
        event.settings.set('attendee_names_asked', True)
        event.settings.set('name_scheme', 'title_given_middle_family')
        event.settings.set('locales', ['en', 'de'])
        event.checkin_lists.create(name="Default", all_products=True)

        order_paid = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PAID,
            datetime=datetime.datetime(2019, 2, 22, 14, 0, 0, tzinfo=pytz.UTC), expires=now() + datetime.timedelta(days=10),
            total=33, locale='en'
        )
        item_ticket = Item.objects.create(event=event, name="Ticket", default_price=23, admission=True)
        OrderPosition.objects.create(
            order=order_paid,
            item=item_ticket,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={"title": "Mr", "given_name": "Peter", "middle_name": "A", "family_name": "Jones"},
            secret='hutjztuxhkbtwnesv2suqv26k6ttytxx'
        )
        OrderPosition.objects.create(
            order=order_paid,
            item=item_ticket,
            variation=None,
            price=Decimal("13"),
            attendee_name_parts={"title": "Mrs", "given_name": "Andrea", "middle_name": "J", "family_name": "Zulu"},
            secret='ggsngqtnmhx74jswjngw3fk8pfwz2a7k'
        )
        yield event


def clean(d):
    return d.replace("\r", "").replace("\n", "")


@pytest.mark.django_db
def test_csv_simple(event):
    c = CSVCheckinList(event)
    _, _, content = c.render({
        'list': event.checkin_lists.first().pk,
        'secrets': True,
        'sort': 'name',
        '_format': 'default',
        'questions': []
    })
    assert clean(content.decode()) == clean(""""Order code","Attendee name","Attendee name: Title","Attendee name:
 First name","Attendee name: Middle name","Attendee name: Family name","Product","Price","Checked in","Checked out","Automatically
 checked in","Secret","E-mail","Company","Voucher code","Order date","Requires special attention","Comment","Seat ID","Seat name",
"Seat zone","Seat row","Seat number","Address","ZIP code","City","Country","State"
"FOO","Mr Peter A Jones","Mr","Peter","A","Jones","Ticket","23.00","","","No","hutjztuxhkbtwnesv2suqv26k6ttytxx",
"dummy@dummy.test","","","2019-02-22","No","","","","","","","","","","",""
"FOO","Mrs Andrea J Zulu","Mrs","Andrea","J","Zulu","Ticket","13.00","","","No","ggsngqtnmhx74jswjngw3fk8pfwz2a7k",
"dummy@dummy.test","","","2019-02-22","No","","","","","","","","","","",""
""")


@pytest.mark.django_db
def test_csv_order_by_name_parts(event):  # noqa
    from django.conf import settings
    if not settings.JSON_FIELD_AVAILABLE:
        raise pytest.skip("Not supported on this database")
    c = CSVCheckinList(event)
    _, _, content = c.render({
        'list': event.checkin_lists.first().pk,
        'secrets': True,
        'sort': 'name:given_name',
        '_format': 'default',
        'questions': []
    })
    assert clean(content.decode()) == clean(""""Order code","Attendee name","Attendee name: Title",
"Attendee name: First name","Attendee name: Middle name","Attendee name: Family name","Product","Price",
"Checked in","Checked out","Automatically checked in","Secret","E-mail","Company","Voucher code","Order date","Requires special
 attention","Comment","Seat ID","Seat name","Seat zone","Seat row","Seat number","Address","ZIP code","City","Country","State"
"FOO","Mrs Andrea J Zulu","Mrs","Andrea","J","Zulu","Ticket","13.00","","","No","ggsngqtnmhx74jswjngw3fk8pfwz2a7k",
"dummy@dummy.test","","","2019-02-22","No","","","","","","","","","","",""
"FOO","Mr Peter A Jones","Mr","Peter","A","Jones","Ticket","23.00","","","No","hutjztuxhkbtwnesv2suqv26k6ttytxx",
"dummy@dummy.test","","","2019-02-22","No","","","","","","","","","","",""
""")
    c = CSVCheckinList(event)
    _, _, content = c.render({
        'list': event.checkin_lists.first().pk,
        'secrets': True,
        'sort': 'name:family_name',
        '_format': 'default',
        'questions': []
    })
    assert clean(content.decode()) == clean(""""Order code","Attendee name","Attendee name: Title",
"Attendee name: First name","Attendee name: Middle name","Attendee name: Family name","Product","Price",
"Checked in","Checked out","Automatically checked in","Secret","E-mail","Company","Voucher code","Order date","Requires special
 attention","Comment","Seat ID","Seat name","Seat zone","Seat row","Seat number","Address","ZIP code","City","Country","State"
"FOO","Mr Peter A Jones","Mr","Peter","A","Jones","Ticket","23.00","","","No","hutjztuxhkbtwnesv2suqv26k6ttytxx",
"dummy@dummy.test","","","2019-02-22","No","","","","","","","","","","",""
"FOO","Mrs Andrea J Zulu","Mrs","Andrea","J","Zulu","Ticket","13.00","","","No","ggsngqtnmhx74jswjngw3fk8pfwz2a7k",
"dummy@dummy.test","","","2019-02-22","No","","","","","","","","","","",""
""")


@pytest.mark.django_db
def test_csv_order_by_inherited_name_parts(event):  # noqa
    from django.conf import settings
    if not settings.JSON_FIELD_AVAILABLE:
        raise pytest.skip("Not supported on this database")

    with scope(organizer=event.organizer):
        OrderPosition.objects.filter(attendee_name_cached__icontains="Andrea").delete()
        op = OrderPosition.objects.get()
        op.attendee_name_parts = {}
        op.save()
        order2 = Order.objects.create(
            code='BAR', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PAID,
            datetime=datetime.datetime(2019, 2, 22, 14, 0, 0, tzinfo=pytz.UTC), expires=now() + datetime.timedelta(days=10),
            total=33, locale='en'
        )
        OrderPosition.objects.create(
            order=order2,
            item=event.items.first(),
            variation=None,
            company='BARCORP',
            price=Decimal("23"),
            secret='hutjztuxhkbtwnesv2suqv26k6ttytyy'
        )
        InvoiceAddress.objects.create(
            order=event.orders.get(code='BAR'),
            company='FOOCORP',
            name_parts={"title": "Mr", "given_name": "Albert", "middle_name": "J", "family_name": "Zulu", "_scheme": "title_given_middle_family"}
        )
        InvoiceAddress.objects.create(
            order=event.orders.get(code='FOO'),
            company='FOOCORP',
            name_parts={"title": "Mr", "given_name": "Paul", "middle_name": "A", "family_name": "Jones", "_scheme": "title_given_middle_family"}
        )

    c = CSVCheckinList(event)
    _, _, content = c.render({
        'list': event.checkin_lists.first().pk,
        'secrets': True,
        'sort': 'name',
        '_format': 'default',
        'questions': []
    })
    assert clean(content.decode()) == clean(""""Order code","Attendee name","Attendee name: Title",
"Attendee name: First name","Attendee name: Middle name","Attendee name: Family name","Product","Price",
"Checked in","Checked out","Automatically checked in","Secret","E-mail","Company","Voucher code","Order date","Requires special
 attention","Comment","Seat ID","Seat name","Seat zone","Seat row","Seat number","Address","ZIP code","City","Country","State"
"BAR","Mr Albert J Zulu","Mr","Albert","J","Zulu","Ticket","23.00","","","No","hutjztuxhkbtwnesv2suqv26k6ttytyy",
"dummy@dummy.test","BARCORP","","2019-02-22","No","","","","","","","","","","",""
"FOO","Mr Paul A Jones","Mr","Paul","A","Jones","Ticket","23.00","","","No","hutjztuxhkbtwnesv2suqv26k6ttytxx",
"dummy@dummy.test","FOOCORP","","2019-02-22","No","","","","","","","","","","",""
""")
    c = CSVCheckinList(event)
    _, _, content = c.render({
        'list': event.checkin_lists.first().pk,
        'secrets': True,
        'sort': 'name:given_name',
        '_format': 'default',
        'questions': []
    })
    assert clean(content.decode()) == clean(""""Order code","Attendee name","Attendee name: Title",
"Attendee name: First name","Attendee name: Middle name","Attendee name: Family name","Product","Price",
"Checked in","Checked out","Automatically checked in","Secret","E-mail","Company","Voucher code","Order date","Requires special
 attention","Comment","Seat ID","Seat name","Seat zone","Seat row","Seat number","Address","ZIP code","City","Country","State"
"BAR","Mr Albert J Zulu","Mr","Albert","J","Zulu","Ticket","23.00","","","No","hutjztuxhkbtwnesv2suqv26k6ttytyy",
"dummy@dummy.test","BARCORP","","2019-02-22","No","","","","","","","","","","",""
"FOO","Mr Paul A Jones","Mr","Paul","A","Jones","Ticket","23.00","","","No","hutjztuxhkbtwnesv2suqv26k6ttytxx",
"dummy@dummy.test","FOOCORP","","2019-02-22","No","","","","","","","","","","",""
""")
    c = CSVCheckinList(event)
    _, _, content = c.render({
        'list': event.checkin_lists.first().pk,
        'secrets': True,
        'sort': 'name:family_name',
        '_format': 'default',
        'questions': []
    })
    assert clean(content.decode()) == clean(""""Order code","Attendee name","Attendee name: Title",
"Attendee name: First name","Attendee name: Middle name","Attendee name: Family name","Product","Price",
"Checked in","Checked out","Automatically checked in","Secret","E-mail","Company","Voucher code","Order date","Requires special
 attention","Comment","Seat ID","Seat name","Seat zone","Seat row","Seat number","Address","ZIP code","City","Country","State"
"FOO","Mr Paul A Jones","Mr","Paul","A","Jones","Ticket","23.00","","","No","hutjztuxhkbtwnesv2suqv26k6ttytxx",
"dummy@dummy.test","FOOCORP","","2019-02-22","No","","","","","","","","","","",""
"BAR","Mr Albert J Zulu","Mr","Albert","J","Zulu","Ticket","23.00","","","No","hutjztuxhkbtwnesv2suqv26k6ttytyy",
"dummy@dummy.test","BARCORP","","2019-02-22","No","","","","","","","","","","",""
""")
