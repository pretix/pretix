from datetime import datetime, timedelta

import pytest
from django.utils.timezone import now
from django_redis import get_redis_connection
from django_scopes import scopes_disabled
from pytz import UTC

from pretix.base.models import Event, Item, Organizer, Quota


@pytest.fixture(autouse=True)
def autoskip(request, settings):
    if 'redis' not in settings.ORIGINAL_CACHES:
        pytest.skip("can only be run with redis")
    if 'sqlite3' in settings.DATABASES['default']['ENGINE']:
        pytest.skip("cannot be run on sqlite")
    if not request.config.getvalue("reuse_db"):
        pytest.skip("only works with --reuse-db due to some weird connection handling bug")


@pytest.fixture(autouse=True)
def cleared_redis(settings):
    settings.HAS_REDIS = True
    settings.CACHES = settings.ORIGINAL_CACHES
    redis = get_redis_connection("redis")
    redis.flushall()


@pytest.fixture
@scopes_disabled()
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
@scopes_disabled()
def event(organizer):
    e = Event.objects.create(
        organizer=organizer, name='Dummy', slug='dummy',
        date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC),
        presale_end=now() + timedelta(days=300),
        plugins='pretix.plugins.banktransfer,pretix.plugins.ticketoutputpdf',
        is_public=True, live=True
    )
    e.item_meta_properties.create(name="day", default="Monday")
    e.settings.timezone = 'Europe/Berlin'
    return e


@pytest.fixture
@scopes_disabled()
def item(event):
    return Item.objects.create(
        event=event,
        name='Regular ticket',
        default_price=0,
    )


@pytest.fixture
@scopes_disabled()
def quota(event, item):
    q = Quota.objects.create(
        event=event,
        size=10,
        name='Regular tickets'
    )
    q.items.add(item)
    return q
