import json
from datetime import timedelta

import pytest
from _decimal import Decimal
from django.utils.timezone import now

from pretix.base.models import Event, Order, OrderPosition, Organizer
from pretix.base.shredder import (
    AttendeeNameShredder, EmailAddressShredder, WaitingListShredder,
)


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


@pytest.fixture
def item(event):
    return event.items.create(
        name='Early-bird ticket',
        category=None, default_price=23,
        admission=True
    )


@pytest.fixture
def order(event, item):
    o = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=14, payment_provider='banktransfer', locale='en'
    )
    event.settings.set('attendee_names_asked', True)
    event.settings.set('locales', ['en', 'de'])
    OrderPosition.objects.create(
        order=o,
        item=item,
        variation=None,
        price=Decimal("14"),
        attendee_name="Peter",
        attendee_email="foo@example.org"
    )
    return o


@pytest.mark.django_db
def test_email_shredder(event, order):
    l1 = order.log_action(
        'pretix.event.order.email.expired',
        data={
            'recipient': 'dummy@dummy.test',
            'message': 'Hello Peter@,',
            'subject': 'Foo'
        }
    )
    l2 = order.log_action(
        'pretix.event.order.contact.changed',
        data={
            'old_email': 'dummy@dummy.test',
            'new_email': 'foo@bar.com',
        }
    )

    s = EmailAddressShredder(event)
    f = list(s.generate_files())
    assert json.loads(f[0][2]) == {
        order.code: 'dummy@dummy.test'
    }
    assert json.loads(f[1][2]) == {
        '{}-{}'.format(order.code, 1): 'foo@example.org'
    }
    s.shred_data()
    order.refresh_from_db()
    assert order.email is None
    assert order.positions.first().attendee_email is None
    l1.refresh_from_db()
    assert '@' not in l1.data
    assert 'Foo' in l1.data
    l2.refresh_from_db()
    assert '@' not in l2.data
    # TODO: attendee_name change logs


@pytest.mark.django_db
def test_waitinglist_shredder(event, item):
    q = event.quotas.create(size=5)
    q.items.add(item)
    wle = event.waitinglistentries.create(
        item=item, email='foo@example.org'
    )
    wle.send_voucher()
    assert '@' in wle.voucher.comment
    assert '@' in wle.voucher.all_logentries().last().data
    s = WaitingListShredder(event)
    f = list(s.generate_files())
    assert json.loads(f[0][2]) == [
        {
            'id': wle.pk,
            'item': item.pk,
            'variation': None,
            'subevent': None,
            'voucher': wle.voucher.pk,
            'created': wle.created.isoformat().replace('+00:00', 'Z'),
            'locale': 'en',
            'email': 'foo@example.org'
        }
    ]
    s.shred_data()
    wle.refresh_from_db()
    wle.voucher.refresh_from_db()
    assert '@' not in wle.email
    assert '@' not in wle.voucher.comment
    assert '@' not in wle.voucher.all_logentries().last().data


@pytest.mark.django_db
def test_attendee_name_shredder(event, order):
    s = AttendeeNameShredder(event)
    f = list(s.generate_files())
    assert json.loads(f[0][2]) == {
        '{}-{}'.format(order.code, 1): 'Peter'
    }
    s.shred_data()
    order.refresh_from_db()
    assert order.positions.first().attendee_name is None
    # TODO: Logs of name changes

# TODO: invoice addresses
# TODO: question answers
# TODO: invoices
# TODO: cached tickets
# TODO: payment info
# TODO: order meta
# TODO: log entries
