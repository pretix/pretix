import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import Event, Organizer
from pretix.base.secrets import (
    RandomTicketSecretGenerator, Sig1TicketSecretGenerator,
)

schemes = (
    (RandomTicketSecretGenerator, False),
    (Sig1TicketSecretGenerator, True),
)


@pytest.fixture(scope='function')
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(),
        plugins='pretix.plugins.banktransfer'
    )
    with scope(organizer=o):
        yield event


@pytest.mark.django_db
@pytest.mark.parametrize("scheme", schemes)
def test_force_invalidate(event, scheme):
    item = event.items.create(name="Foo", default_price=0)
    generator, input_dependent = scheme
    g = generator(event)

    first = g.generate_secret(item, None, None, current_secret=None, force_invalidate=False)
    assert first
    second = g.generate_secret(item, None, None, current_secret=first, force_invalidate=True)
    assert first != second


@pytest.mark.django_db
@pytest.mark.parametrize("scheme", schemes)
def test_keep_same(event, scheme):
    item = event.items.create(name="Foo", default_price=0)
    generator, input_dependent = scheme
    g = generator(event)

    first = g.generate_secret(item, None, None, current_secret=None, force_invalidate=False)
    assert first
    second = g.generate_secret(item, None, None, current_secret=first, force_invalidate=False)
    assert first == second


@pytest.mark.django_db
@pytest.mark.parametrize("scheme", schemes)
def test_change_if_required(event, scheme):
    item = event.items.create(name="Foo", default_price=0)
    item2 = event.items.create(name="Bar", default_price=0)
    generator, input_dependent = scheme
    g = generator(event)

    first = g.generate_secret(item, None, None, current_secret=None, force_invalidate=False)
    assert first
    second = g.generate_secret(item2, None, None, current_secret=first, force_invalidate=False)
    if input_dependent:
        assert first != second
    else:
        assert first == second


@pytest.mark.django_db
@pytest.mark.parametrize("scheme", schemes)
def test_change_if_invalid(event, scheme):
    item = event.items.create(name="Foo", default_price=0)
    generator, input_dependent = scheme
    g = generator(event)

    first = "blafasel"
    second = g.generate_secret(item, None, None, current_secret=first, force_invalidate=False)
    if input_dependent:
        assert first != second
