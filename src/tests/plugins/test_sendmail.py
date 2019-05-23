import datetime

import pytest
from django.core import mail as djmail
from django.utils.timezone import now

from pretix.base.models import (
    Event, Item, Order, OrderPosition, Organizer, Team, User,
)


@pytest.fixture
def event():
    """Returns an event instance"""
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(),
        plugins='pretix.plugins.sendmail,tests.testdummy',
    )
    return event


@pytest.fixture
def item(event):
    """Returns an item instance"""
    return Item.objects.create(name='Test item', event=event, default_price=13)


@pytest.fixture
def order(item):
    """Returns an order instance"""
    o = Order.objects.create(event=item.event, status=Order.STATUS_PENDING,
                             expires=now() + datetime.timedelta(hours=1),
                             total=13, code='DUMMY', email='dummy@dummy.test',
                             datetime=now(), locale='en')
    OrderPosition.objects.create(order=o, item=item, price=13)
    return o


@pytest.fixture
def logged_in_client(client, event):
    """Returns a logged client"""
    user = User.objects.create_superuser('dummy@dummy.dummy', 'dummy')
    t = Team.objects.create(organizer=event.organizer, can_view_orders=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)
    client.force_login(user)
    return client


@pytest.fixture
def sendmail_url(event):
    """Returns a url for sendmail"""
    url = '/control/event/{orga}/{event}/sendmail/'.format(
        event=event.slug, orga=event.organizer.slug,
    )
    return url


@pytest.mark.django_db
def test_sendmail_view(logged_in_client, sendmail_url, expected=200):
    response = logged_in_client.get(sendmail_url)

    assert response.status_code == expected


@pytest.mark.django_db
def test_sendmail_simple_case(logged_in_client, sendmail_url, event, order):
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'n',
                                      'recipients': 'orders',
                                      'items': order.positions.first().item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.'
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [order.email]
    assert djmail.outbox[0].subject == 'Test subject'
    assert 'This is a test file for sending mails.' in djmail.outbox[0].body

    url = sendmail_url + 'history/'
    response = logged_in_client.get(url)

    assert response.status_code == 200
    assert 'Test subject' in response.rendered_content


@pytest.mark.django_db
def test_sendmail_email_not_sent_if_order_not_match(logged_in_client, sendmail_url, event, order):
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'p',
                                      'recipients': 'orders',
                                      'items': order.positions.first().item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.'
                                      },
                                     follow=True)
    assert 'alert-danger' in response.rendered_content

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_sendmail_preview(logged_in_client, sendmail_url, event, order):
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'n',
                                      'recipients': 'orders',
                                      'items': order.positions.first().item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      'action': 'preview'
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'E-mail preview' in response.rendered_content

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_sendmail_invalid_data(logged_in_client, sendmail_url, event, order):
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'n',
                                      'recipients': 'orders',
                                      'items': order.positions.first().item_id,
                                      'subject_0': 'Test subject',
                                      },
                                     follow=True)

    assert 'has-error' in response.rendered_content

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_sendmail_multi_locales(logged_in_client, sendmail_url, event, item):
    djmail.outbox = []

    event.settings.set('locales', ['en', 'de'])

    o = Order.objects.create(event=item.event, status=Order.STATUS_PAID,
                             expires=now() + datetime.timedelta(hours=1),
                             total=13, code='DUMMY', email='dummy@dummy.test',
                             datetime=now(),
                             locale='de')
    OrderPosition.objects.create(order=o, item=item, price=13)

    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'p',
                                      'recipients': 'orders',
                                      'items': item.pk,
                                      'subject_0': 'Test subject',
                                      'message_0': 'Test message',
                                      'subject_1': 'Benutzer',
                                      'message_1': 'Test nachricht'
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [o.email]
    assert djmail.outbox[0].subject == 'Benutzer'
    assert 'Test nachricht' in djmail.outbox[0].body

    url = sendmail_url + 'history/'
    response = logged_in_client.get(url)

    assert response.status_code == 200
    assert 'Benutzer' in response.rendered_content
    assert 'Test nachricht' in response.rendered_content


@pytest.mark.django_db
def test_sendmail_subevents(logged_in_client, sendmail_url, event, order):
    event.has_subevents = True
    event.save()
    se1 = event.subevents.create(name='Subevent FOO', date_from=now())
    se2 = event.subevents.create(name='Bar', date_from=now())
    op = order.positions.last()
    op.subevent = se1
    op.save()

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'n',
                                      'recipients': 'orders',
                                      'items': order.positions.first().item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      'subevent': se1.pk
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 1

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'n',
                                      'recipients': 'orders',
                                      'items': order.positions.first().item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      'subevent': se2.pk
                                      },
                                     follow=True)
    assert len(djmail.outbox) == 0

    url = sendmail_url + 'history/'
    response = logged_in_client.get(url)

    assert response.status_code == 200
    assert 'Subevent FOO' in response.rendered_content


@pytest.mark.django_db
def test_sendmail_placeholder(logged_in_client, sendmail_url, event, order):
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'n',
                                      'recipients': 'orders',
                                      'items': order.positions.first().item_id,
                                      'subject_0': '{code} Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      'action': 'preview'
                                      },
                                     follow=True)

    assert response.status_code == 200
    assert 'ORDER1234' in response.rendered_content

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_sendmail_attendee_mails(logged_in_client, sendmail_url, event, order):
    p = order.positions.first()
    event.settings.attendee_emails_asked = True
    p.attendee_email = 'attendee@dummy.test'
    p.save()

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'n',
                                      'recipients': 'attendees',
                                      'items': order.positions.first().item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.'
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ['attendee@dummy.test']
    assert '/ticket/' in djmail.outbox[0].body
    assert '/order/' not in djmail.outbox[0].body


@pytest.mark.django_db
def test_sendmail_both_mails(logged_in_client, sendmail_url, event, order):
    p = order.positions.first()
    event.settings.attendee_emails_asked = True
    p.attendee_email = 'attendee@dummy.test'
    p.save()

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'n',
                                      'recipients': 'both',
                                      'items': order.positions.first().item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.'
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 2
    assert djmail.outbox[0].to == ['attendee@dummy.test']
    assert '/ticket/' in djmail.outbox[0].body
    assert '/order/' not in djmail.outbox[0].body
    assert djmail.outbox[1].to == ['dummy@dummy.test']
    assert '/ticket/' not in djmail.outbox[1].body
    assert '/order/' in djmail.outbox[1].body


@pytest.mark.django_db
def test_sendmail_both_but_same_address(logged_in_client, sendmail_url, event, order):
    p = order.positions.first()
    event.settings.attendee_emails_asked = True
    p.attendee_email = 'dummy@dummy.test'
    p.save()

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'n',
                                      'recipients': 'both',
                                      'items': order.positions.first().item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.'
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ['dummy@dummy.test']
    assert '/ticket/' not in djmail.outbox[0].body
    assert '/order/' in djmail.outbox[0].body


@pytest.mark.django_db
def test_sendmail_attendee_fallback(logged_in_client, sendmail_url, event, order):
    p = order.positions.first()
    event.settings.attendee_emails_asked = True
    p.attendee_email = None
    p.save()

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'n',
                                      'recipients': 'attendees',
                                      'items': order.positions.first().item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.'
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ['dummy@dummy.test']
    assert '/ticket/' not in djmail.outbox[0].body
    assert '/order/' in djmail.outbox[0].body


@pytest.mark.django_db
def test_sendmail_attendee_product_filter(logged_in_client, sendmail_url, event, order):
    event.settings.attendee_emails_asked = True
    i2 = Item.objects.create(name='Test item', event=event, default_price=13)
    p = order.positions.first()
    p.attendee_email = 'attendee1@dummy.test'
    p.save()
    order.positions.create(
        item=i2, price=0, attendee_email='attendee2@dummy.test'
    )

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url,
                                     {'sendto': 'n',
                                      'recipients': 'attendees',
                                      'items': i2.pk,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.'
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ['attendee2@dummy.test']
    assert '/ticket/' in djmail.outbox[0].body
    assert '/order/' not in djmail.outbox[0].body
