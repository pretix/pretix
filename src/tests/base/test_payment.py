import datetime
from decimal import Decimal

import pytest
import pytz
from django.utils.timezone import now
from django_scopes import scope
from tests.testdummy.payment import DummyPaymentProvider

from pretix.base.models import (
    CartPosition, Event, Item, Order, OrderPosition, Organizer,
)
from pretix.base.reldate import RelativeDate, RelativeDateWrapper


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    with scope(organizer=o):
        yield event


@pytest.mark.django_db
def test_payment_fee_forward(event):
    prov = DummyPaymentProvider(event)
    prov.settings.set('_fee_abs', Decimal('0.30'))
    prov.settings.set('_fee_percent', Decimal('5.00'))
    prov.settings.set('_fee_reverse_calc', False)
    assert prov.calculate_fee(Decimal('100.00')) == Decimal('5.30')


@pytest.mark.django_db
def test_payment_fee_reverse_percent(event):
    prov = DummyPaymentProvider(event)
    prov.settings.set('_fee_abs', Decimal('0.00'))
    prov.settings.set('_fee_percent', Decimal('5.00'))
    prov.settings.set('_fee_reverse_calc', True)
    assert prov.calculate_fee(Decimal('100.00')) == Decimal('5.26')


@pytest.mark.django_db
def test_payment_fee_reverse_percent_and_abs(event):
    prov = DummyPaymentProvider(event)
    prov.settings.set('_fee_abs', Decimal('0.30'))
    prov.settings.set('_fee_percent', Decimal('2.90'))
    prov.settings.set('_fee_reverse_calc', True)
    assert prov.calculate_fee(Decimal('100.00')) == Decimal('3.30')


@pytest.mark.django_db
def test_payment_fee_reverse_percent_and_abs_default(event):
    prov = DummyPaymentProvider(event)
    prov.settings.set('_fee_abs', Decimal('0.30'))
    prov.settings.set('_fee_percent', Decimal('2.90'))
    assert prov.calculate_fee(Decimal('100.00')) == Decimal('3.30')


@pytest.mark.django_db
def test_availability_date_available(event):
    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', datetime.date.today() + datetime.timedelta(days=1))
    result = prov._is_still_available()
    assert result


@pytest.mark.django_db
def test_availability_date_not_available(event):
    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', datetime.date.today() - datetime.timedelta(days=1))
    result = prov._is_still_available()
    assert not result


@pytest.mark.django_db
def test_availability_date_relative(event):
    event.settings.set('timezone', 'US/Pacific')
    tz = pytz.timezone('US/Pacific')
    event.date_from = tz.localize(datetime.datetime(2016, 12, 3, 12, 0, 0))
    event.save()
    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', RelativeDateWrapper(
        RelativeDate(days_before=2, time=None, base_date_name='date_from')
    ))

    utc = pytz.timezone('UTC')
    assert prov._is_still_available(tz.localize(datetime.datetime(2016, 11, 30, 23, 0, 0)).astimezone(utc))
    assert prov._is_still_available(tz.localize(datetime.datetime(2016, 12, 1, 23, 59, 0)).astimezone(utc))
    assert not prov._is_still_available(tz.localize(datetime.datetime(2016, 12, 2, 0, 0, 1)).astimezone(utc))


@pytest.mark.django_db
def test_availability_date_timezones(event):
    event.settings.set('timezone', 'US/Pacific')
    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', '2016-12-01')

    tz = pytz.timezone('US/Pacific')
    utc = pytz.timezone('UTC')
    assert prov._is_still_available(tz.localize(datetime.datetime(2016, 11, 30, 23, 0, 0)).astimezone(utc))
    assert prov._is_still_available(tz.localize(datetime.datetime(2016, 12, 1, 23, 59, 0)).astimezone(utc))
    assert not prov._is_still_available(tz.localize(datetime.datetime(2016, 12, 2, 0, 0, 1)).astimezone(utc))


@pytest.mark.django_db
def test_availability_date_cart_relative_subevents(event):
    event.date_from = now() + datetime.timedelta(days=5)
    event.has_subevents = True
    event.save()
    tr7 = event.tax_rules.create(rate=Decimal('7.00'))
    ticket = Item.objects.create(event=event, name='Early-bird ticket', tax_rule=tr7,
                                 default_price=Decimal('23.00'), admission=True)

    se1 = event.subevents.create(name="SE1", date_from=now() + datetime.timedelta(days=10))
    se2 = event.subevents.create(name="SE2", date_from=now() + datetime.timedelta(days=3))

    CartPosition.objects.create(
        item=ticket, price=23, expires=now() + datetime.timedelta(days=1), subevent=se1, event=event, cart_id="123"
    )
    CartPosition.objects.create(
        item=ticket, price=23, expires=now() + datetime.timedelta(days=1), subevent=se2, event=event, cart_id="123"
    )

    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', RelativeDateWrapper(
        RelativeDate(days_before=3, time=None, base_date_name='date_from')
    ))
    assert prov._is_still_available(cart_id="123")

    prov.settings.set('_availability_date', RelativeDateWrapper(
        RelativeDate(days_before=4, time=None, base_date_name='date_from')
    ))
    assert not prov._is_still_available(cart_id="123")


@pytest.mark.django_db
def test_availability_date_order_relative_subevents(event):
    event.date_from = now() + datetime.timedelta(days=5)
    event.has_subevents = True
    event.save()
    tr7 = event.tax_rules.create(rate=Decimal('7.00'))
    ticket = Item.objects.create(event=event, name='Early-bird ticket', tax_rule=tr7,
                                 default_price=Decimal('23.00'), admission=True)

    se1 = event.subevents.create(name="SE1", date_from=now() + datetime.timedelta(days=10))
    se2 = event.subevents.create(name="SE2", date_from=now() + datetime.timedelta(days=3))

    order = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + datetime.timedelta(days=10),
        total=Decimal('46.00'),
    )
    OrderPosition.objects.create(
        order=order, item=ticket, variation=None, subevent=se1,
        price=Decimal("23.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
    )
    OrderPosition.objects.create(
        order=order, item=ticket, variation=None, subevent=se2,
        price=Decimal("23.00"), attendee_name_parts={'full_name': "Dieter"}, positionid=2
    )

    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', RelativeDateWrapper(
        RelativeDate(days_before=3, time=None, base_date_name='date_from')
    ))
    assert prov._is_still_available(order=order)

    prov.settings.set('_availability_date', RelativeDateWrapper(
        RelativeDate(days_before=4, time=None, base_date_name='date_from')
    ))
    assert not prov._is_still_available(order=order)
