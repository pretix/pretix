import datetime
from decimal import Decimal

import pytest
import pytz
from django.utils.timezone import now
from tests.testdummy.payment import DummyPaymentProvider

from pretix.base.models import Event, Organizer


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


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
def test_availability_date_timezones(event):
    event.settings.set('timezone', 'US/Pacific')
    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', '2016-12-01')

    tz = pytz.timezone('US/Pacific')
    utc = pytz.timezone('UTC')
    assert prov._is_still_available(tz.localize(datetime.datetime(2016, 11, 30, 23, 0, 0)).astimezone(utc))
    assert prov._is_still_available(tz.localize(datetime.datetime(2016, 12, 1, 23, 59, 0)).astimezone(utc))
    assert not prov._is_still_available(tz.localize(datetime.datetime(2016, 12, 2, 0, 0, 1)).astimezone(utc))
