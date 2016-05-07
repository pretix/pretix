from datetime import timedelta

import pytest
from django.utils.timezone import now

from pretix.base.models import Event, Order, Organizer
from pretix.base.payment import FreeOrderProvider
from pretix.base.services.orders import _create_order, expire_orders


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


@pytest.mark.django_db
def test_expiry_days(event):
    today = now()
    event.settings.set('payment_term_days', 5)
    order = _create_order(event, email='dummy@example.org', positions=[],
                          dt=today, payment_provider=FreeOrderProvider(event),
                          locale='de')
    assert (order.expires - today).days == 5


@pytest.mark.django_db
def test_expiry_last(event):
    today = now()
    event.settings.set('payment_term_days', 5)
    event.settings.set('payment_term_last', now() + timedelta(days=3))
    order = _create_order(event, email='dummy@example.org', positions=[],
                          dt=today, payment_provider=FreeOrderProvider(event),
                          locale='de')
    assert (order.expires - today).days == 3
    event.settings.set('payment_term_last', now() + timedelta(days=7))
    order = _create_order(event, email='dummy@example.org', positions=[],
                          dt=today, payment_provider=FreeOrderProvider(event),
                          locale='de')
    assert (order.expires - today).days == 5


@pytest.mark.django_db
def test_expiring(event):
    o1 = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0, payment_provider='banktransfer'
    )
    o2 = Order.objects.create(
        code='FO2', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() - timedelta(days=10),
        total=0, payment_provider='banktransfer'
    )
    expire_orders(None)
    o1 = Order.objects.get(id=o1.id)
    assert o1.status == Order.STATUS_PENDING
    o2 = Order.objects.get(id=o2.id)
    assert o2.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_expiring_auto_disabled(event):
    event.settings.set('payment_term_expire_automatically', False)
    o1 = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0, payment_provider='banktransfer'
    )
    o2 = Order.objects.create(
        code='FO2', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() - timedelta(days=10),
        total=0, payment_provider='banktransfer'
    )
    expire_orders(None)
    o1 = Order.objects.get(id=o1.id)
    assert o1.status == Order.STATUS_PENDING
    o2 = Order.objects.get(id=o2.id)
    assert o2.status == Order.STATUS_PENDING
