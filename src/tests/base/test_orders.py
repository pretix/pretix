from datetime import timedelta

import pytest
from django.utils.timezone import now

from pretix.base.models import Event, Organizer
from pretix.base.payment import FreeOrderProvider
from pretix.base.services.orders import _create_order


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
