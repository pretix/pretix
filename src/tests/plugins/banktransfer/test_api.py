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
import copy
import json
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, Item, Order, OrderPosition, Organizer, Quota, Team, User,
)
from pretix.plugins.banktransfer.models import BankImportJob, BankTransaction


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    t = Team.objects.create(organizer=event.organizer, can_view_orders=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)
    o1 = Order.objects.create(
        code='1Z3AS', event=event,
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23
    )
    o2 = Order.objects.create(
        code='6789Z', event=event,
        status=Order.STATUS_CANCELED,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23
    )
    quota = Quota.objects.create(name="Test", size=2, event=event)
    item1 = Item.objects.create(event=event, name="Ticket", default_price=23)
    quota.items.add(item1)
    OrderPosition.objects.create(order=o1, item=item1, variation=None, price=23)
    return event, user, o1, o2


RES_JOB = {
    'event': 'dummy',
    'id': 1,
    'transactions': [
        {'comment': '',
         'message': '',
         'payer': 'Foo',
         'reference': '',
         'checksum': '',
         'iban': '',
         'bic': '',
         'amount': '0.00',
         'date': 'unknown',
         'state': 'error',
         'currency': 'EUR',
         'order': None
         }
    ],
    'created': '2017-06-27T09:13:35.785251Z',
    'state': 'pending',
    'currency': 'EUR'
}


@pytest.mark.django_db
def test_api_list(env, client):
    testtime = datetime(2017, 12, 1, 10, 0, 0, tzinfo=timezone.utc)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        job = BankImportJob.objects.create(event=env[0], organizer=env[0].organizer, currency='EUR')
        BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                       state=BankTransaction.STATE_ERROR,
                                       amount=0, date='unknown', currency='EUR')
    res = copy.copy(RES_JOB)
    res['id'] = job.pk
    res['created'] = testtime.isoformat().replace('+00:00', 'Z')
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(
        client.get('/api/v1/organizers/{}/bankimportjobs/'.format(env[0].organizer.slug)).content.decode('utf-8')
    )
    assert r['results'] == [res]


@pytest.mark.django_db
def test_api_detail(env, client):
    testtime = datetime(2017, 12, 1, 10, 0, 0, tzinfo=timezone.utc)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        job = BankImportJob.objects.create(event=env[0], organizer=env[0].organizer, currency='EUR')
        BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                       state=BankTransaction.STATE_ERROR,
                                       amount=0, date='unknown', currency='EUR')
    res = copy.copy(RES_JOB)
    res['id'] = job.pk
    res['created'] = testtime.isoformat().replace('+00:00', 'Z')
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(
        client.get(
            '/api/v1/organizers/{}/bankimportjobs/{}/'.format(env[0].organizer.slug, job.pk)
        ).content.decode('utf-8')
    )
    assert r == res


@pytest.mark.django_db(transaction=True)
def test_api_create(env, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post(
        '/api/v1/organizers/{}/bankimportjobs/'.format(env[0].organizer.slug), json.dumps({
            'event': 'dummy',
            'transactions': [
                {
                    'payer': 'Foo',
                    'reference': 'DUMMY-1Z3AS',
                    'amount': '23.00',
                    'date': 'yesterday'  # test bogus date format
                }
            ]
        }), content_type="application/json"
    )
    assert r.status_code == 201
    rdata = json.loads(r.content.decode('utf-8'))
    # This is only because we don't run celery in tests, otherwise it wouldn't be completed yet.
    assert rdata['state'] == 'completed'
    assert len(rdata['transactions']) == 1
    assert rdata['transactions'][0]['checksum']
    assert rdata['transactions'][0]['currency'] == 'EUR'
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db(transaction=True)
def test_api_create_with_iban_bic(env, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post(
        '/api/v1/organizers/{}/bankimportjobs/'.format(env[0].organizer.slug), json.dumps({
            'event': 'dummy',
            'transactions': [
                {
                    'payer': 'Foo',
                    'reference': 'DUMMY-1Z3AS',
                    'amount': '23.00',
                    'iban': 'NL79RABO5373380466',
                    'bic': 'GENODEM1GLS',
                    'date': 'yesterday'  # test bogus date format
                }
            ]
        }), content_type="application/json"
    )
    assert r.status_code == 201
    rdata = json.loads(r.content.decode('utf-8'))
    # This is only because we don't run celery in tests, otherwise it wouldn't be completed yet.
    assert rdata['state'] == 'completed'
    assert len(rdata['transactions']) == 1
    assert rdata['transactions'][0]['checksum']
    assert rdata['transactions'][0]['currency'] == 'EUR'
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID
    with scopes_disabled():
        assert env[2].payments.first().info_data['iban'] == 'NL79RABO5373380466'


@pytest.mark.django_db(transaction=True)
def test_api_create_org_auto_currency(env, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post(
        '/api/v1/organizers/{}/bankimportjobs/'.format(env[0].organizer.slug), json.dumps({
            'transactions': [
                {
                    'payer': 'Foo',
                    'reference': 'DUMMY-1Z3AS',
                    'amount': '23.00',
                    'date': 'yesterday'  # test bogus date format
                }
            ]
        }), content_type="application/json"
    )
    assert r.status_code == 201
    rdata = json.loads(r.content.decode('utf-8'))
    # This is only because we don't run celery in tests, otherwise it wouldn't be completed yet.
    assert rdata['state'] == 'completed'
    assert len(rdata['transactions']) == 1
    assert rdata['transactions'][0]['checksum']
    assert rdata['transactions'][0]['currency'] == 'EUR'
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db(transaction=True)
def test_api_create_org_unclear_currency(env, client):
    Event.objects.create(
        organizer=env[0].organizer, name='Dummy', slug='dummy2', currency='HUF',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post(
        '/api/v1/organizers/{}/bankimportjobs/'.format(env[0].organizer.slug), json.dumps({
            'transactions': [
                {
                    'payer': 'Foo',
                    'reference': 'DUMMY-1Z3AS',
                    'amount': '23.00',
                    'date': 'yesterday'  # test bogus date format
                }
            ]
        }), content_type="application/json"
    )
    assert r.status_code == 400

    r = client.post(
        '/api/v1/organizers/{}/bankimportjobs/'.format(env[0].organizer.slug), json.dumps({
            'currency': 'EUR',
            'transactions': [
                {
                    'payer': 'Foo',
                    'reference': 'DUMMY-1Z3AS',
                    'amount': '23.00',
                    'date': 'yesterday'  # test bogus date format
                }
            ]
        }), content_type="application/json"
    )
    assert r.status_code == 201
    rdata = json.loads(r.content.decode('utf-8'))
    # This is only because we don't run celery in tests, otherwise it wouldn't be completed yet.
    assert rdata['state'] == 'completed'
    assert len(rdata['transactions']) == 1
    assert rdata['transactions'][0]['checksum']
    assert rdata['transactions'][0]['currency'] == 'EUR'
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID
