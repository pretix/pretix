#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Daniel, Flavia Bastos, Sanket Dasgupta, Tobias Kunze,
# pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import datetime

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Checkin, Item, Order, OrderPosition, Team, User


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


@pytest.fixture
def subevent(event):
    event.has_subevents = True
    event.save()
    se = event.subevents.create(name='se1', date_from=now())
    return se


@pytest.fixture
def waitinglistentry(event, item):
    return event.waitinglistentries.create(
        item=item,
        created=now(),
        email='john@example.org',
    )


@pytest.mark.django_db
def test_sendmail_view(logged_in_client, sendmail_url, expected=200):
    response = logged_in_client.get(sendmail_url + 'orders/')

    assert response.status_code == expected


@pytest.mark.django_db
def test_sendmail_simple_case(logged_in_client, sendmail_url, event, order, pos):
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'orders',
                                      'items': pos.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
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
def test_sendmail_email_not_sent_if_order_not_match(logged_in_client, sendmail_url, event, order, pos):
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'p',
                                      'action': 'send',
                                      'recipients': 'orders',
                                      'items': pos.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      },
                                     follow=True)
    assert 'alert-danger' in response.rendered_content

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_sendmail_preview(logged_in_client, sendmail_url, event, order, pos):
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'recipients': 'orders',
                                      'items': pos.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      'action': 'preview',
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'E-mail preview' in response.rendered_content

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_sendmail_invalid_data(logged_in_client, sendmail_url, event, order, pos):
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'orders',
                                      'items': pos.item_id,
                                      'subject_0': 'Test subject',
                                      },
                                     follow=True)

    assert 'has-error' in response.rendered_content

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_sendmail_multi_locales(logged_in_client, sendmail_url, event, item):
    djmail.outbox = []

    event.settings.set('locales', ['en', 'de'])

    with scopes_disabled():
        o = Order.objects.create(event=item.event, status=Order.STATUS_PAID,
                                 expires=now() + datetime.timedelta(hours=1),
                                 total=13, code='DUMMY', email='dummy@dummy.test',
                                 datetime=now(),
                                 locale='de')
        OrderPosition.objects.create(order=o, item=item, price=13)

    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'p',
                                      'action': 'send',
                                      'recipients': 'orders',
                                      'items': item.pk,
                                      'subject_0': 'Test subject',
                                      'message_0': 'Test message',
                                      'subject_1': 'Benutzer',
                                      'message_1': 'Test nachricht',
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
def test_sendmail_subevents(logged_in_client, sendmail_url, event, order, pos):
    event.has_subevents = True
    event.save()
    with scopes_disabled():
        se1 = event.subevents.create(name='Subevent FOO', date_from=now())
        se2 = event.subevents.create(name='Bar', date_from=now())
        op = order.positions.last()
    op.subevent = se1
    op.save()

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'orders',
                                      'items': pos.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      'subevent': se1.pk,
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 1

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'orders',
                                      'items': pos.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      'subevent': se2.pk,
                                      },
                                     follow=True)
    assert len(djmail.outbox) == 0

    url = sendmail_url + 'history/'
    response = logged_in_client.get(url)

    assert response.status_code == 200
    assert 'Subevent FOO' in response.rendered_content


@pytest.mark.django_db
def test_sendmail_placeholder(logged_in_client, sendmail_url, event, order, pos):
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'recipients': 'orders',
                                      'items': pos.item_id,
                                      'subject_0': '{code} Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      'action': 'preview',
                                      },
                                     follow=True)

    assert response.status_code == 200
    assert 'F8VVL' in response.rendered_content

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_sendmail_attendee_mails(logged_in_client, sendmail_url, event, order, pos):
    p = pos
    event.settings.attendee_emails_asked = True
    p.attendee_email = 'attendee@dummy.test'
    p.save()

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'attendees',
                                      'items': pos.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ['attendee@dummy.test']
    assert '/ticket/' in djmail.outbox[0].body
    assert '/order/' not in djmail.outbox[0].body


@pytest.mark.django_db
def test_sendmail_both_mails(logged_in_client, sendmail_url, event, order, pos):
    p = pos
    event.settings.attendee_emails_asked = True
    p.attendee_email = 'attendee@dummy.test'
    p.save()

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'both',
                                      'items': pos.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
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
def test_sendmail_both_but_same_address(logged_in_client, sendmail_url, event, order, pos):
    p = pos
    event.settings.attendee_emails_asked = True
    p.attendee_email = 'dummy@dummy.test'
    p.save()

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'both',
                                      'items': pos.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ['dummy@dummy.test']
    assert '/ticket/' not in djmail.outbox[0].body
    assert '/order/' in djmail.outbox[0].body


@pytest.mark.django_db
def test_sendmail_attendee_fallback(logged_in_client, sendmail_url, event, order, pos):
    p = pos
    event.settings.attendee_emails_asked = True
    p.attendee_email = None
    p.save()

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'attendees',
                                      'items': pos.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ['dummy@dummy.test']
    assert '/ticket/' not in djmail.outbox[0].body
    assert '/order/' in djmail.outbox[0].body


@pytest.mark.django_db
def test_sendmail_attendee_product_filter(logged_in_client, sendmail_url, event, order, pos):
    event.settings.attendee_emails_asked = True
    with scopes_disabled():
        i2 = Item.objects.create(name='Test item', event=event, default_price=13)
        p = pos
        p.attendee_email = 'attendee1@dummy.test'
        p.save()
        order.positions.create(
            item=i2, price=0, attendee_email='attendee2@dummy.test'
        )

        djmail.outbox = []
        response = logged_in_client.post(sendmail_url + 'orders/',
                                         {'sendto': 'na',
                                          'action': 'send',
                                          'recipients': 'attendees',
                                          'items': i2.pk,
                                          'subject_0': 'Test subject',
                                          'message_0': 'This is a test file for sending mails.',
                                          },
                                         follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ['attendee2@dummy.test']
    assert '/ticket/' in djmail.outbox[0].body
    assert '/order/' not in djmail.outbox[0].body


@pytest.mark.django_db
def test_sendmail_attendee_checkin_filter(logged_in_client, sendmail_url, event, order, checkin_list, item, pos):
    event.settings.attendee_emails_asked = True
    with scopes_disabled():
        chkl2 = event.checkin_lists.create(name="Test Checkinlist 2", all_products=True)
        p = pos
        p.attendee_email = 'attendee1@dummy.test'
        p.save()
        pos2 = order.positions.create(item=item, price=0, attendee_email='attendee2@dummy.test')
        Checkin.objects.create(position=pos2, list=chkl2)

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'attendees',
                                      'items': pos2.item_id,
                                      'filter_checkins': 'on',
                                      'checkin_lists': [chkl2.id],
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

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'attendees',
                                      'items': pos2.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      'filter_checkins': 'on',
                                      'not_checked_in': 'on',
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ['attendee1@dummy.test']
    assert '/ticket/' in djmail.outbox[0].body
    assert '/order/' not in djmail.outbox[0].body

    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'attendees',
                                      'items': pos2.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      'filter_checkins': 'on',
                                      'checkin_lists': [chkl2.id],
                                      'not_checked_in': 'on',
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 2
    assert djmail.outbox[0].to == ['attendee1@dummy.test']
    assert djmail.outbox[1].to == ['attendee2@dummy.test']

    # Test that filtering is ignored if filter_checkins is not set
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'attendees',
                                      'items': pos2.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      'not_checked_in': 'on',
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 2
    assert '/ticket/' in djmail.outbox[0].body
    assert '/order/' not in djmail.outbox[0].body
    assert '/ticket/' in djmail.outbox[1].body
    assert '/order/' not in djmail.outbox[1].body
    to_emails = set(*zip(*[mail.to for mail in djmail.outbox]))
    assert to_emails == {'attendee1@dummy.test', 'attendee2@dummy.test'}

    # Test that filtering is ignored if filter_checkins is not set
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'orders/',
                                     {'sendto': 'na',
                                      'action': 'send',
                                      'recipients': 'attendees',
                                      'items': pos2.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      'checkin_lists': [chkl2.id],
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content
    assert len(djmail.outbox) == 2
    assert '/ticket/' in djmail.outbox[0].body
    assert '/order/' not in djmail.outbox[0].body
    assert '/ticket/' in djmail.outbox[1].body
    assert '/order/' not in djmail.outbox[1].body
    to_emails = set(*zip(*[mail.to for mail in djmail.outbox]))
    assert to_emails == {'attendee1@dummy.test', 'attendee2@dummy.test'}


@pytest.mark.django_db
def test_waitinglist_sendmail_simple_case(logged_in_client, sendmail_url, event, waitinglistentry):
    djmail.outbox = []
    response = logged_in_client.post(sendmail_url + 'waitinglist/',
                                     {'action': 'send',
                                      'items': waitinglistentry.item_id,
                                      'subject_0': 'Test subject',
                                      'message_0': 'This is a test file for sending mails.',
                                      },
                                     follow=True)
    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [waitinglistentry.email]
    assert djmail.outbox[0].subject == 'Test subject'
    assert 'This is a test file for sending mails.' in djmail.outbox[0].body

    url = sendmail_url + 'history/'
    response = logged_in_client.get(url)

    assert response.status_code == 200
    assert 'Test subject' in response.rendered_content
