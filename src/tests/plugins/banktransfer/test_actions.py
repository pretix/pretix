import json
from datetime import timedelta

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, Item, Order, OrderPayment, OrderPosition, OrderRefund, Organizer,
    Quota, Team, User,
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
        total=23,
    )
    o2 = Order.objects.create(
        code='6789Z', event=event,
        status=Order.STATUS_CANCELED,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23,
    )
    quota = Quota.objects.create(name="Test", size=2, event=event)
    item1 = Item.objects.create(event=event, name="Ticket", default_price=23)
    quota.items.add(item1)
    OrderPosition.objects.create(order=o1, item=item1, variation=None, price=23)
    return event, user, o1, o2


@pytest.mark.django_db
def test_discard(env, client):
    job = BankImportJob.objects.create(event=env[0])
    trans = BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_ERROR,
                                           amount=0, date='unknown')
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(client.post('/control/event/{}/{}/banktransfer/action/'.format(env[0].organizer.slug, env[0].slug), {
        'action_{}'.format(trans.pk): 'discard',
    }).content.decode('utf-8'))
    assert r['status'] == 'ok'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_DISCARDED
    assert trans.payer == ''


@pytest.mark.django_db
def test_assign_order(env, client):
    job = BankImportJob.objects.create(event=env[0])
    trans = BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_NOMATCH,
                                           amount=23, date='unknown')
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(client.post('/control/event/{}/{}/banktransfer/action/'.format(env[0].organizer.slug, env[0].slug), {
        'action_{}'.format(trans.pk): 'assign:{}'.format(env[2].code),
    }).content.decode('utf-8'))
    assert r['status'] == 'ok'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_VALID
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_assign_order_unknown(env, client):
    job = BankImportJob.objects.create(event=env[0])
    trans = BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_NOMATCH,
                                           amount=23, date='unknown')
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(client.post('/control/event/{}/{}/banktransfer/action/'.format(env[0].organizer.slug, env[0].slug), {
        'action_{}'.format(trans.pk): 'assign:FOO'
    }).content.decode('utf-8'))
    assert r['status'] == 'error'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_NOMATCH


@pytest.mark.django_db
def test_assign_order_amount_incorrect(env, client):
    job = BankImportJob.objects.create(event=env[0])
    trans = BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_NOMATCH,
                                           amount=12, date='unknown')
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(client.post('/control/event/{}/{}/banktransfer/action/'.format(env[0].organizer.slug, env[0].slug), {
        'action_{}'.format(trans.pk): 'assign:{}'.format(env[2].code)
    }).content.decode('utf-8'))
    assert r['status'] == 'ok'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_VALID


@pytest.mark.django_db
def test_comment(env, client):
    job = BankImportJob.objects.create(event=env[0])
    trans = BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_NOMATCH,
                                           amount=12, date='unknown')
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(client.post('/control/event/{}/{}/banktransfer/action/'.format(env[0].organizer.slug, env[0].slug), {
        'action_{}'.format(trans.pk): 'comment:This is my comment'.format(env[2].code)
    }).content.decode('utf-8'))
    assert r['status'] == 'ok'
    trans.refresh_from_db()
    assert trans.comment == 'This is my comment'
    assert trans.state == BankTransaction.STATE_NOMATCH


@pytest.mark.django_db
def test_retry_success(env, client):
    job = BankImportJob.objects.create(event=env[0])
    trans = BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_DUPLICATE,
                                           amount=23, date='unknown', order=env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    env[3].status = Order.STATUS_PENDING
    env[3].save()
    r = json.loads(client.post('/control/event/{}/{}/banktransfer/action/'.format(env[0].organizer.slug, env[0].slug), {
        'action_{}'.format(trans.pk): 'retry',
    }).content.decode('utf-8'))
    assert r['status'] == 'ok'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_VALID
    env[3].refresh_from_db()
    assert env[3].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_retry_canceled(env, client):
    job = BankImportJob.objects.create(event=env[0])
    trans = BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_ERROR,
                                           amount=23, date='unknown', order=env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(client.post('/control/event/{}/{}/banktransfer/action/'.format(env[0].organizer.slug, env[0].slug), {
        'action_{}'.format(trans.pk): 'retry',
    }).content.decode('utf-8'))
    assert r['status'] == 'error'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_ERROR
    env[3].refresh_from_db()
    assert env[3].status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_retry_refunded(env, client):
    job = BankImportJob.objects.create(event=env[0])
    trans = BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_ERROR,
                                           amount=23, date='unknown', order=env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    env[3].status = Order.STATUS_CANCELED
    env[3].save()
    r = json.loads(client.post('/control/event/{}/{}/banktransfer/action/'.format(env[0].organizer.slug, env[0].slug), {
        'action_{}'.format(trans.pk): 'retry',
    }).content.decode('utf-8'))
    assert r['status'] == 'error'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_ERROR
    env[3].refresh_from_db()
    assert env[3].status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_retry_paid(env, client):
    job = BankImportJob.objects.create(event=env[0])
    trans = BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_ERROR,
                                           amount=23, date='unknown', order=env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    env[3].status = Order.STATUS_PAID
    env[3].save()
    r = json.loads(client.post('/control/event/{}/{}/banktransfer/action/'.format(env[0].organizer.slug, env[0].slug), {
        'action_{}'.format(trans.pk): 'retry',
    }).content.decode('utf-8'))
    assert r['status'] == 'error'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_ERROR
    env[3].refresh_from_db()
    assert env[3].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_assign_order_organizer(env, client):
    job = BankImportJob.objects.create(organizer=env[0].organizer)
    trans = BankTransaction.objects.create(organizer=env[0].organizer, import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_NOMATCH,
                                           amount=23, date='unknown')
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(client.post('/control/organizer/{}/banktransfer/action/'.format(env[0].organizer.slug), {
        'action_{}'.format(trans.pk): 'assign:{}'.format(env[2].code),
    }).content.decode('utf-8'))
    assert r['status'] == 'ok'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_VALID
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_assign_order_organizer_full_code(env, client):
    job = BankImportJob.objects.create(organizer=env[0].organizer)
    trans = BankTransaction.objects.create(organizer=env[0].organizer, import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_NOMATCH,
                                           amount=23, date='unknown')
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(client.post('/control/organizer/{}/banktransfer/action/'.format(env[0].organizer.slug), {
        'action_{}'.format(trans.pk): 'assign:{}-{}'.format(env[0].slug.upper(), env[2].code),
    }).content.decode('utf-8'))
    assert r['status'] == 'ok'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_VALID
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_assign_order_organizer_no_permission(env, client):
    job = BankImportJob.objects.create(organizer=env[0].organizer)
    trans = BankTransaction.objects.create(organizer=env[0].organizer, import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_NOMATCH,
                                           amount=23, date='unknown')
    team = env[1].teams.first()
    team.can_change_orders = False
    team.save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post('/control/organizer/{}/banktransfer/action/'.format(env[0].organizer.slug), {
        'action_{}'.format(trans.pk): 'assign:{}-{}'.format(env[0].slug.upper(), env[2].code),
    })
    assert r.status_code == 403


@pytest.mark.django_db
def test_assign_order_organizer_no_permission_for_event(env, client):
    job = BankImportJob.objects.create(organizer=env[0].organizer)
    trans = BankTransaction.objects.create(organizer=env[0].organizer, import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_NOMATCH,
                                           amount=23, date='unknown')
    team = env[1].teams.first()
    team.limit_events.clear()
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = json.loads(client.post('/control/organizer/{}/banktransfer/action/'.format(env[0].organizer.slug), {
        'action_{}'.format(trans.pk): 'assign:{}-{}'.format(env[0].slug.upper(), env[2].code),
    }).content.decode('utf-8'))
    assert r['status'] == 'error'


@pytest.mark.django_db
def test_retry_refund(env, client):
    job = BankImportJob.objects.create(event=env[0])
    trans = BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_ERROR,
                                           amount=-23, date='unknown', order=env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    env[3].status = Order.STATUS_PAID
    env[3].save()
    r = json.loads(client.post('/control/event/{}/{}/banktransfer/action/'.format(env[0].organizer.slug, env[0].slug), {
        'action_{}'.format(trans.pk): 'retry',
    }).content.decode('utf-8'))
    assert r['status'] == 'error'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_ERROR


@pytest.mark.django_db
def test_retry_refund_external(env, client):
    job = BankImportJob.objects.create(event=env[0])
    trans = BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_ERROR,
                                           amount=-23, date='unknown', order=env[3])
    with scopes_disabled():
        p = env[3].payments.create(amount=23, provider='banktransfer', state=OrderPayment.PAYMENT_STATE_CONFIRMED)
    client.login(email='dummy@dummy.dummy', password='dummy')
    env[3].status = Order.STATUS_PAID
    env[3].save()
    r = json.loads(client.post('/control/event/{}/{}/banktransfer/action/'.format(env[0].organizer.slug, env[0].slug), {
        'action_{}'.format(trans.pk): 'retry',
    }).content.decode('utf-8'))
    assert r['status'] == 'ok'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_VALID
    env[3].refresh_from_db()
    assert env[3].status == Order.STATUS_PAID
    with scopes_disabled():
        r = env[3].refunds.first()
    assert r
    assert r.provider == "banktransfer"
    assert r.amount == 23
    assert r.payment == p
    assert r.state == OrderRefund.REFUND_STATE_EXTERNAL


@pytest.mark.django_db
def test_retry_refund_complete(env, client):
    job = BankImportJob.objects.create(event=env[0])
    trans = BankTransaction.objects.create(event=env[0], import_job=job, payer='Foo',
                                           state=BankTransaction.STATE_ERROR,
                                           amount=-23, date='unknown', order=env[3])
    with scopes_disabled():
        env[3].payments.create(amount=23, provider='banktransfer', state=OrderPayment.PAYMENT_STATE_CONFIRMED)
        ref = env[3].refunds.create(amount=23, provider='manual', state=OrderRefund.REFUND_STATE_CREATED)
    client.login(email='dummy@dummy.dummy', password='dummy')
    env[3].status = Order.STATUS_CANCELED
    env[3].save()
    r = json.loads(client.post('/control/event/{}/{}/banktransfer/action/'.format(env[0].organizer.slug, env[0].slug), {
        'action_{}'.format(trans.pk): 'retry',
    }).content.decode('utf-8'))
    assert r['status'] == 'ok'
    trans.refresh_from_db()
    assert trans.state == BankTransaction.STATE_VALID
    env[3].refresh_from_db()
    assert env[3].status == Order.STATUS_CANCELED
    ref.refresh_from_db()
    assert ref.provider == "manual"
    assert ref.amount == 23
    assert ref.payment is None
    assert ref.state == OrderRefund.REFUND_STATE_DONE
