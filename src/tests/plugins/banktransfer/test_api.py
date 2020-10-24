import copy
import json
from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled
from pytz import UTC

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
         'order': None
         }
    ],
    'created': '2017-06-27T09:13:35.785251Z',
    'state': 'pending'
}


@pytest.mark.django_db
def test_api_list(env, client):
    testtime = datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        job = BankImportJob.objects.create(event=env[0], organizer=env[0].organizer)
        BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                       state=BankTransaction.STATE_ERROR,
                                       amount=0, date='unknown')
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
    testtime = datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        job = BankImportJob.objects.create(event=env[0], organizer=env[0].organizer)
        BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                       state=BankTransaction.STATE_ERROR,
                                       amount=0, date='unknown')
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
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID
    with scopes_disabled():
        assert env[2].payments.first().info_data['iban'] == 'NL79RABO5373380466'
