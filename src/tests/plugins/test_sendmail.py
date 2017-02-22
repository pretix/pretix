import datetime

import pytest

from django.utils.timezone import now

from pretix.base.models import (
    Event, EventPermission, Item, ItemCategory, Order, OrderPosition,
    Organizer, OrganizerPermission, User,
)


@pytest.fixture
def event():
    '''Returns an event instance'''
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(),
        plugins='pretix.plugins.sendmail,tests.testdummy',
    )
    return event


@pytest.fixture
def item(event):
    '''Returns an item instance'''
    return Item.objects.create(name='Test item', event=event, default_price=13)


@pytest.fixture
def item_category(event):
    '''Returns an item category instance'''
    return ItemCategory.objects.create(event=event)


@pytest.fixture
def order(item):
    '''Returns an order instance'''
    o = Order.objects.create(event=item.event, status=Order.STATUS_PENDING,
                             expires=now() + datetime.timedelta(hours=1),
                             total=13, code='DUMMY', email='dummy@dummy.test',
                             datetime=now(), payment_provider='banktransfer')
    OrderPosition.objects.create(order=o, item=item, price=13)
    return o


@pytest.fixture
def logged_in_client(client, event):
    '''Returns a logged client'''
    user = User.objects.create_superuser('dummy@dummy.dummy', 'dummy')
    OrganizerPermission.objects.create(organizer=event.organizer, user=user, can_create_events=True)
    EventPermission.objects.create(event=event, user=user, can_change_items=True,
                                   can_change_settings=True, can_change_orders=True, can_view_orders=True)
    client.force_login(user)
    return client


@pytest.mark.parametrize('url,expected', [
    ('/control/event/{orga}/{event}/sendmail/', 200),
])
@pytest.mark.django_db
def test_sendmail_view(logged_in_client, url, expected, event):
    url = url.format(
        event=event.slug, orga=event.organizer.slug,
    )
    response = logged_in_client.get(url)

    assert response.status_code == expected
