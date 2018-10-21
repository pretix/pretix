from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from bs4 import BeautifulSoup
from django.core import mail
from django.utils.timezone import now
from django_countries.fields import Country
from tests.base import SoupTest
from tests.plugins.stripe.test_provider import MockedCharge

from pretix.base.models import (
    Event, InvoiceAddress, Item, Order, OrderPayment, OrderPosition,
    OrderRefund, Organizer, Question, QuestionAnswer, Quota, Team, User,
)
from pretix.base.payment import PaymentException
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice,
)


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.stripe,tests.testdummy'
    )
    event.settings.set('ticketoutput_testdummy__enabled', True)
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    t = Team.objects.create(organizer=o, can_view_orders=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)
    o = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=14, locale='en'
    )
    o.payments.create(
        amount=o.total, provider='banktransfer', state=OrderPayment.PAYMENT_STATE_PENDING
    )
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 category=None, default_price=23,
                                 admission=True)
    event.settings.set('attendee_names_asked', True)
    event.settings.set('locales', ['en', 'de'])
    OrderPosition.objects.create(
        order=o,
        item=ticket,
        variation=None,
        price=Decimal("14"),
        attendee_name_parts={'full_name': "Peter"}
    )
    return event, user, o, ticket


@pytest.mark.django_db
def test_order_list(client, env):
    otherticket = Item.objects.create(event=env[0], name='Early-bird ticket',
                                      category=None, default_price=23,
                                      admission=True)
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?query=peter')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?query=hans')
    assert 'FOO' not in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?query=dummy')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?status=p')
    assert 'FOO' not in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?status=n')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?status=ne')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?item=%s' % otherticket.id)
    assert 'FOO' not in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?item=%s' % env[3].id)
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?provider=free')
    assert 'FOO' not in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?provider=banktransfer')
    assert 'FOO' in response.rendered_content

    response = client.get('/control/event/dummy/dummy/orders/?status=o')
    assert 'FOO' not in response.rendered_content
    env[2].expires = now() - timedelta(days=10)
    env[2].save()
    response = client.get('/control/event/dummy/dummy/orders/?status=o')
    assert 'FOO' in response.rendered_content

    response = client.get('/control/event/dummy/dummy/orders/?status=pa')
    assert 'FOO' not in response.rendered_content
    env[2].require_approval = True
    env[2].save()
    response = client.get('/control/event/dummy/dummy/orders/?status=pa')
    assert 'FOO' in response.rendered_content

    q = Question.objects.create(event=env[0], question="Q", type="N", required=True)
    q.items.add(env[3])
    op = env[2].positions.first()
    qa = QuestionAnswer.objects.create(question=q, orderposition=op, answer="12")
    response = client.get('/control/event/dummy/dummy/orders/?question=%d&answer=12' % q.pk)
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?question=%d&answer=13' % q.pk)
    assert 'FOO' not in response.rendered_content

    q.type = "C"
    q.save()
    qo1 = q.options.create(answer="Foo")
    qo2 = q.options.create(answer="Bar")
    qa.options.add(qo1)
    response = client.get('/control/event/dummy/dummy/orders/?question=%d&answer=%d' % (q.pk, qo1.pk))
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?question=%d&answer=%d' % (q.pk, qo2.pk))
    assert 'FOO' not in response.rendered_content


@pytest.mark.django_db
def test_order_detail(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/')
    assert 'Early-bird' in response.rendered_content
    assert 'Peter' in response.rendered_content


@pytest.mark.django_db
def test_order_set_contact(client, env):
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/orders/FOO/contact', {
        'email': 'admin@rami.io'
    })
    o = Order.objects.get(id=env[2].id)
    assert o.email == 'admin@rami.io'


@pytest.mark.django_db
def test_order_set_locale(client, env):
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/orders/FOO/locale', {
        'locale': 'de'
    })
    o = Order.objects.get(id=env[2].id)
    assert o.locale == 'de'


@pytest.mark.django_db
def test_order_set_locale_with_invalid_locale_value(client, env):
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/orders/FOO/locale', {
        'locale': 'fr'
    })
    o = Order.objects.get(id=env[2].id)
    assert o.locale == 'en'


@pytest.mark.django_db
def test_order_set_comment(client, env):
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/orders/FOO/comment', {
        'comment': 'Foo'
    })
    o = Order.objects.get(id=env[2].id)
    assert o.comment == 'Foo'


@pytest.mark.django_db
def test_order_transition_to_expired_success(client, env):
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'e'
    })
    o = Order.objects.get(id=env[2].id)
    assert o.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_transition_to_paid_in_time_success(client, env):
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'p'
    })
    o = Order.objects.get(id=env[2].id)
    assert o.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_transition_to_paid_expired_quota_left(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_EXPIRED
    o.save()
    q = Quota.objects.create(event=env[0], size=10)
    q.items.add(env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    res = client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'p'
    })
    o = Order.objects.get(id=env[2].id)
    assert res.status_code < 400
    assert o.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_approve(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PENDING
    o.require_approval = True
    o.save()
    q = Quota.objects.create(event=env[0], size=10)
    q.items.add(env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    res = client.post('/control/event/dummy/dummy/orders/FOO/approve', {
    })
    o = Order.objects.get(id=env[2].id)
    assert res.status_code < 400
    assert o.status == Order.STATUS_PENDING
    assert not o.require_approval


@pytest.mark.django_db
def test_order_deny(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PENDING
    o.require_approval = True
    o.save()
    q = Quota.objects.create(event=env[0], size=10)
    q.items.add(env[3])
    client.login(email='dummy@dummy.dummy', password='dummy')
    res = client.post('/control/event/dummy/dummy/orders/FOO/deny', {
    })
    o = Order.objects.get(id=env[2].id)
    assert res.status_code < 400
    assert o.status == Order.STATUS_CANCELED
    assert o.require_approval


@pytest.mark.django_db
@pytest.mark.parametrize("process", [
    # (Old status, new status, success expected)
    (Order.STATUS_CANCELED, Order.STATUS_PAID, False),
    (Order.STATUS_CANCELED, Order.STATUS_PENDING, False),
    (Order.STATUS_CANCELED, Order.STATUS_REFUNDED, False),
    (Order.STATUS_CANCELED, Order.STATUS_EXPIRED, False),

    (Order.STATUS_PAID, Order.STATUS_PENDING, False),
    (Order.STATUS_PAID, Order.STATUS_CANCELED, False),
    (Order.STATUS_PAID, Order.STATUS_REFUNDED, False),
    (Order.STATUS_PAID, Order.STATUS_EXPIRED, False),

    (Order.STATUS_PENDING, Order.STATUS_CANCELED, True),
    (Order.STATUS_PENDING, Order.STATUS_PAID, True),
    (Order.STATUS_PENDING, Order.STATUS_REFUNDED, False),
    (Order.STATUS_PENDING, Order.STATUS_EXPIRED, True),

    (Order.STATUS_REFUNDED, Order.STATUS_CANCELED, False),
    (Order.STATUS_REFUNDED, Order.STATUS_PAID, False),
    (Order.STATUS_REFUNDED, Order.STATUS_PENDING, False),
    (Order.STATUS_REFUNDED, Order.STATUS_EXPIRED, False),
])
def test_order_transition(client, env, process):
    o = Order.objects.get(id=env[2].id)
    o.status = process[0]
    o.save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.get('/control/event/dummy/dummy/orders/FOO/transition?status=' + process[1])
    client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': process[1]
    })
    o = Order.objects.get(id=env[2].id)
    if process[2]:
        assert o.status == process[1]
    else:
        assert o.status == process[0]


@pytest.mark.django_db
def test_order_cancel_free(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PAID
    o.total = Decimal('0.00')
    o.save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.get('/control/event/dummy/dummy/orders/FOO/transition?status=c')
    client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'c'
    })
    o = Order.objects.get(id=env[2].id)
    assert o.status == Order.STATUS_CANCELED


@pytest.mark.django_db
def test_order_invoice_create_forbidden(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    env[0].settings.set('invoice_generate', 'no')
    response = client.post('/control/event/dummy/dummy/orders/FOO/invoice', {}, follow=True)
    assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_order_invoice_create_duplicate(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    generate_invoice(env[2])
    env[0].settings.set('invoice_generate', 'admin')
    response = client.post('/control/event/dummy/dummy/orders/FOO/invoice', {}, follow=True)
    assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_order_invoice_create_ok(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    env[0].settings.set('invoice_generate', 'admin')
    response = client.post('/control/event/dummy/dummy/orders/FOO/invoice', {}, follow=True)
    assert 'alert-success' in response.rendered_content
    assert env[2].invoices.exists()


@pytest.mark.django_db
def test_order_invoice_regenerate(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    i = generate_invoice(env[2])
    InvoiceAddress.objects.create(name='Foo', order=env[2])
    env[0].settings.set('invoice_generate', 'admin')
    response = client.post('/control/event/dummy/dummy/orders/FOO/invoices/%d/regenerate' % i.pk, {}, follow=True)
    assert 'alert-success' in response.rendered_content
    i.refresh_from_db()
    assert 'Foo' in i.invoice_to
    assert env[2].invoices.exists()


@pytest.mark.django_db
def test_order_invoice_regenerate_canceled(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    i = generate_invoice(env[2])
    generate_cancellation(i)
    response = client.post('/control/event/dummy/dummy/orders/FOO/invoices/%d/regenerate' % i.pk, {}, follow=True)
    assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_order_invoice_regenerate_unknown(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/invoices/%d/regenerate' % 3, {}, follow=True)
    assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_order_invoice_reissue(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    i = generate_invoice(env[2])
    InvoiceAddress.objects.create(name='Foo', order=env[2])
    env[0].settings.set('invoice_generate', 'admin')
    response = client.post('/control/event/dummy/dummy/orders/FOO/invoices/%d/reissue' % i.pk, {}, follow=True)
    assert 'alert-success' in response.rendered_content
    i.refresh_from_db()
    assert env[2].invoices.count() == 3
    assert 'Foo' not in env[2].invoices.all()[0].invoice_to
    assert 'Foo' not in env[2].invoices.all()[1].invoice_to
    assert 'Foo' in env[2].invoices.all()[2].invoice_to


@pytest.mark.django_db
def test_order_invoice_reissue_canceled(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    i = generate_invoice(env[2])
    generate_cancellation(i)
    response = client.post('/control/event/dummy/dummy/orders/FOO/invoices/%d/reissue' % i.pk, {}, follow=True)
    assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_order_invoice_reissue_unknown(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/invoices/%d/reissue' % 3, {}, follow=True)
    assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_order_resend_link(client, env):
    mail.outbox = []
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/resend', {}, follow=True)
    assert 'alert-success' in response.rendered_content
    assert 'FOO' in mail.outbox[0].body


@pytest.mark.django_db
def test_order_extend_not_pending(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_PAID
    o.save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/extend', follow=True)
    assert 'alert-danger' in response.rendered_content
    response = client.post('/control/event/dummy/dummy/orders/FOO/extend', follow=True)
    assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_order_extend_not_expired(client, env):
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    newdate = (now() + timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/extend', {
        'expires': newdate
    }, follow=True)
    assert 'alert-success' in response.rendered_content
    o = Order.objects.get(id=env[2].id)
    assert o.expires.strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


@pytest.mark.django_db
def test_order_extend_overdue_quota_empty(client, env):
    o = Order.objects.get(id=env[2].id)
    o.expires = now() - timedelta(days=5)
    o.save()
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    newdate = (now() + timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/extend', {
        'expires': newdate
    }, follow=True)
    assert 'alert-success' in response.rendered_content
    o = Order.objects.get(id=env[2].id)
    assert o.expires.strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"


@pytest.mark.django_db
def test_order_extend_overdue_quota_blocked_by_waiting_list(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_EXPIRED
    o.expires = now() - timedelta(days=5)
    o.save()
    q = Quota.objects.create(event=env[0], size=1)
    q.items.add(env[3])
    env[0].waitinglistentries.create(item=env[3], email='foo@bar.com')

    newdate = (now() + timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/extend', {
        'expires': newdate
    }, follow=True)
    assert 'alert-success' in response.rendered_content
    o = Order.objects.get(id=env[2].id)
    assert o.expires.strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"
    assert o.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_order_extend_expired_quota_left(client, env):
    o = Order.objects.get(id=env[2].id)
    o.expires = now() - timedelta(days=5)
    o.status = Order.STATUS_EXPIRED
    o.save()
    q = Quota.objects.create(event=env[0], size=3)
    q.items.add(env[3])
    newdate = (now() + timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/extend', {
        'expires': newdate
    }, follow=True)
    assert b'alert-success' in response.content
    o = Order.objects.get(id=env[2].id)
    assert o.expires.strftime("%Y-%m-%d %H:%M:%S") == newdate[:10] + " 23:59:59"
    assert o.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_order_extend_expired_quota_empty(client, env):
    o = Order.objects.get(id=env[2].id)
    o.expires = now() - timedelta(days=5)
    o.status = Order.STATUS_EXPIRED
    olddate = o.expires
    o.save()
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    newdate = (now() + timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/extend', {
        'expires': newdate
    }, follow=True)
    assert b'alert-danger' in response.content
    o = Order.objects.get(id=env[2].id)
    assert o.expires.strftime("%Y-%m-%d %H:%M:%S") == olddate.strftime("%Y-%m-%d %H:%M:%S")
    assert o.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_extend_expired_quota_empty_ignore(client, env):
    o = Order.objects.get(id=env[2].id)
    o.expires = now() - timedelta(days=5)
    o.status = Order.STATUS_EXPIRED
    o.save()
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])
    newdate = (now() + timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/extend', {
        'expires': newdate,
        'quota_ignore': 'on'
    }, follow=True)
    assert b'alert-success' in response.content
    o = Order.objects.get(id=env[2].id)
    assert o.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_order_extend_expired_quota_partial(client, env):
    o = Order.objects.get(id=env[2].id)
    OrderPosition.objects.create(
        order=o,
        item=env[3],
        variation=None,
        price=Decimal("14"),
        attendee_name_parts={'full_name': "Peter"}
    )
    o.expires = now() - timedelta(days=5)
    o.status = Order.STATUS_EXPIRED
    olddate = o.expires
    o.save()
    q = Quota.objects.create(event=env[0], size=1)
    q.items.add(env[3])
    newdate = (now() + timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/extend', {
        'expires': newdate
    }, follow=True)
    assert b'alert-danger' in response.content
    o = Order.objects.get(id=env[2].id)
    assert o.expires.strftime("%Y-%m-%d %H:%M:%S") == olddate.strftime("%Y-%m-%d %H:%M:%S")
    assert o.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_mark_paid_overdue_quota_blocked_by_waiting_list(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_EXPIRED
    o.expires = now() - timedelta(days=5)
    o.save()
    q = Quota.objects.create(event=env[0], size=1)
    q.items.add(env[3])
    env[0].waitinglistentries.create(item=env[3], email='foo@bar.com')

    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'p'
    }, follow=True)
    assert 'alert-success' in response.rendered_content
    o = Order.objects.get(id=env[2].id)
    assert o.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_mark_paid_blocked(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_EXPIRED
    o.expires = now() - timedelta(days=5)
    o.save()
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])

    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'p'
    }, follow=True)
    assert 'alert-danger' in response.rendered_content
    o = Order.objects.get(id=env[2].id)
    assert o.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_mark_paid_forced(client, env):
    o = Order.objects.get(id=env[2].id)
    o.status = Order.STATUS_EXPIRED
    o.expires = now() - timedelta(days=5)
    o.save()
    q = Quota.objects.create(event=env[0], size=0)
    q.items.add(env[3])

    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/transition', {
        'status': 'p',
        'force': 'on'
    }, follow=True)
    assert 'alert-success' in response.rendered_content
    o = Order.objects.get(id=env[2].id)
    assert o.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_order_go_lowercase(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/go?code=DuMmyfoO')
    assert response['Location'].endswith('/control/event/dummy/dummy/orders/FOO/')


@pytest.mark.django_db
def test_order_go_with_slug(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/go?code=DUMMYFOO')
    assert response['Location'].endswith('/control/event/dummy/dummy/orders/FOO/')


@pytest.mark.django_db
def test_order_go_found(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/go?code=FOO')
    assert response['Location'].endswith('/control/event/dummy/dummy/orders/FOO/')


@pytest.mark.django_db
def test_order_go_not_found(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/go?code=BAR')
    assert response['Location'].endswith('/control/event/dummy/dummy/orders/')


@pytest.fixture
def order_url(env):
    event = env[0]
    order = env[2]
    url = '/control/event/{orga}/{event}/orders/{code}'.format(
        event=event.slug, orga=event.organizer.slug, code=order.code
    )
    return url


@pytest.mark.django_db
def test_order_sendmail_view(client, order_url):
    client.login(email='dummy@dummy.dummy', password='dummy')
    sendmail_url = order_url + '/sendmail'
    response = client.get(sendmail_url)

    assert response.status_code == 200


@pytest.mark.django_db
def test_order_sendmail_simple_case(client, order_url, env):
    order = env[2]
    client.login(email='dummy@dummy.dummy', password='dummy')
    sendmail_url = order_url + '/sendmail'
    mail.outbox = []
    response = client.post(
        sendmail_url,
        {
            'sendto': order.email,
            'subject': 'Test subject',
            'message': 'This is a test file for sending mails.'
        },
        follow=True)

    assert response.status_code == 200
    assert 'alert-success' in response.rendered_content

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [order.email]
    assert mail.outbox[0].subject == 'Test subject'
    assert 'This is a test file for sending mails.' in mail.outbox[0].body

    mail_history_url = order_url + '/mail_history'
    response = client.get(mail_history_url)

    assert response.status_code == 200
    assert 'Test subject' in response.rendered_content


@pytest.mark.django_db
def test_order_sendmail_preview(client, order_url, env):
    order = env[2]
    client.login(email='dummy@dummy.dummy', password='dummy')
    sendmail_url = order_url + '/sendmail'
    mail.outbox = []
    response = client.post(
        sendmail_url,
        {
            'sendto': order.email,
            'subject': 'Test subject',
            'message': 'This is a test file for sending mails.',
            'action': 'preview'
        },
        follow=True)

    assert response.status_code == 200
    assert 'E-mail preview' in response.rendered_content
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_order_sendmail_invalid_data(client, order_url, env):
    order = env[2]
    client.login(email='dummy@dummy.dummy', password='dummy')
    sendmail_url = order_url + '/sendmail'
    mail.outbox = []
    response = client.post(
        sendmail_url,
        {
            'sendto': order.email,
            'subject': 'Test invalid mail',
        },
        follow=True)

    assert 'has-error' in response.rendered_content
    assert len(mail.outbox) == 0

    mail_history_url = order_url + '/mail_history'
    response = client.get(mail_history_url)

    assert response.status_code == 200
    assert 'Test invalid mail' not in response.rendered_content


class OrderChangeTests(SoupTest):
    def setUp(self):
        super().setUp()
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(organizer=o, name='Dummy', slug='dummy', date_from=now(),
                                          plugins='pretix.plugins.banktransfer')
        self.order = Order.objects.create(
            code='FOO', event=self.event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now() + timedelta(days=10),
            total=Decimal('46.00'),
        )
        self.tr7 = self.event.tax_rules.create(rate=Decimal('7.00'))
        self.tr19 = self.event.tax_rules.create(rate=Decimal('19.00'))
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket', tax_rule=self.tr7,
                                          default_price=Decimal('23.00'), admission=True)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', tax_rule=self.tr19,
                                         default_price=Decimal('12.00'))
        self.op1 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name_parts={'full_name': "Peter"}
        )
        self.op2 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name_parts={'full_name': "Dieter"}
        )
        self.quota = self.event.quotas.create(name="All", size=100)
        self.quota.items.add(self.ticket)
        self.quota.items.add(self.shirt)
        user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        t = Team.objects.create(organizer=o, can_view_orders=True, can_change_orders=True)
        t.members.add(user)
        t.limit_events.add(self.event)
        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_change_item_success(self):
        self.client.post('/control/event/{}/{}/orders/{}/change'.format(
            self.event.organizer.slug, self.event.slug, self.order.code
        ), {
            'op-{}-operation'.format(self.op1.pk): 'product',
            'op-{}-itemvar'.format(self.op1.pk): str(self.shirt.pk),
            'op-{}-operation'.format(self.op2.pk): '',
            'op-{}-itemvar'.format(self.op2.pk): str(self.ticket.pk),
            'add-itemvar'.format(self.op2.pk): str(self.ticket.pk),
        })
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.shirt
        assert self.op1.price == self.shirt.default_price
        assert self.op1.tax_rate == self.shirt.tax_rule.rate
        assert self.order.total == self.op1.price + self.op2.price

    def test_change_subevent_success(self):
        self.event.has_subevents = True
        self.event.save()
        se1 = self.event.subevents.create(name='Foo', date_from=now())
        se2 = self.event.subevents.create(name='Bar', date_from=now())
        self.op1.subevent = se1
        self.op1.save()
        self.op2.subevent = se1
        self.op2.save()
        self.quota.subevent = se1
        self.quota.save()
        q2 = self.event.quotas.create(name='Q2', size=100, subevent=se2)
        q2.items.add(self.ticket)
        q2.items.add(self.shirt)
        self.client.post('/control/event/{}/{}/orders/{}/change'.format(
            self.event.organizer.slug, self.event.slug, self.order.code
        ), {
            'op-{}-operation'.format(self.op1.pk): 'subevent',
            'op-{}-subevent'.format(self.op1.pk): str(se2.pk),
            'op-{}-itemvar'.format(self.op1.pk): str(self.ticket.pk),
            'op-{}-operation'.format(self.op2.pk): '',
            'op-{}-itemvar'.format(self.op2.pk): str(self.ticket.pk),
            'op-{}-subevent'.format(self.op2.pk): str(se1.pk),
            'add-itemvar'.format(self.op2.pk): str(self.ticket.pk),
            'add-subevent'.format(self.op2.pk): str(se1.pk),
        })
        self.op1.refresh_from_db()
        self.op2.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.subevent == se2
        assert self.op2.subevent == se1

    def test_change_price_success(self):
        self.client.post('/control/event/{}/{}/orders/{}/change'.format(
            self.event.organizer.slug, self.event.slug, self.order.code
        ), {
            'op-{}-operation'.format(self.op1.pk): 'price',
            'op-{}-itemvar'.format(self.op1.pk): str(self.ticket.pk),
            'op-{}-price'.format(self.op1.pk): '24.00',
            'op-{}-operation'.format(self.op2.pk): '',
            'op-{}-itemvar'.format(self.op2.pk): str(self.ticket.pk),
            'add-itemvar'.format(self.op2.pk): str(self.ticket.pk),
        })
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.ticket
        assert self.op1.price == Decimal('24.00')
        assert self.order.total == self.op1.price + self.op2.price

    def test_cancel_success(self):
        self.client.post('/control/event/{}/{}/orders/{}/change'.format(
            self.event.organizer.slug, self.event.slug, self.order.code
        ), {
            'op-{}-operation'.format(self.op1.pk): 'cancel',
            'op-{}-itemvar'.format(self.op1.pk): str(self.ticket.pk),
            'op-{}-price'.format(self.op1.pk): str(self.op1.price),
            'op-{}-operation'.format(self.op2.pk): '',
            'op-{}-itemvar'.format(self.op2.pk): str(self.ticket.pk),
            'op-{}-price'.format(self.op2.pk): str(self.op2.price),
            'add-itemvar'.format(self.op2.pk): str(self.ticket.pk),
        })
        self.order.refresh_from_db()
        assert self.order.positions.count() == 1
        assert self.order.total == self.op2.price

    def test_add_item_success(self):
        self.client.post('/control/event/{}/{}/orders/{}/change'.format(
            self.event.organizer.slug, self.event.slug, self.order.code
        ), {
            'op-{}-operation'.format(self.op1.pk): '',
            'op-{}-operation'.format(self.op2.pk): '',
            'op-{}-itemvar'.format(self.op2.pk): str(self.ticket.pk),
            'op-{}-price'.format(self.op2.pk): str(self.op2.price),
            'op-{}-itemvar'.format(self.op1.pk): str(self.ticket.pk),
            'op-{}-price'.format(self.op1.pk): str(self.op1.price),
            'add-itemvar': str(self.shirt.pk),
            'add-do': 'on',
            'add-price': '14.00',
        })
        assert self.order.positions.count() == 3
        assert self.order.positions.last().item == self.shirt
        assert self.order.positions.last().price == 14

    def test_recalculate_reverse_charge(self):
        self.tr7.eu_reverse_charge = True
        self.tr7.home_country = Country('DE')
        self.tr7.save()
        self.tr19.eu_reverse_charge = True
        self.tr19.home_country = Country('DE')
        self.tr19.save()
        InvoiceAddress.objects.create(
            order=self.order, is_business=True, vat_id='ATU1234567', vat_id_validated=True,
            country=Country('AT')
        )

        self.client.post('/control/event/{}/{}/orders/{}/change'.format(
            self.event.organizer.slug, self.event.slug, self.order.code
        ), {
            'other-recalculate_taxes': 'on',
            'add-itemvar'.format(self.op2.pk): str(self.ticket.pk),
            'op-{}-operation'.format(self.op1.pk): '',
            'op-{}-operation'.format(self.op2.pk): '',
            'op-{}-itemvar'.format(self.op2.pk): str(self.ticket.pk),
            'op-{}-price'.format(self.op2.pk): str(self.op2.price),
            'op-{}-itemvar'.format(self.op1.pk): str(self.ticket.pk),
            'op-{}-price'.format(self.op1.pk): str(self.op1.price),
        })

        ops = list(self.order.positions.all())
        for op in ops:
            assert op.price == Decimal('21.50')
            assert op.tax_value == Decimal('0.00')
            assert op.tax_rate == Decimal('0.00')


@pytest.mark.django_db
def test_check_vatid(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    ia = InvoiceAddress.objects.create(order=env[2], is_business=True, vat_id='ATU1234567', country=Country('AT'))
    with mock.patch('vat_moss.id.validate') as mock_validate:
        mock_validate.return_value = ('AT', 'AT123456', 'Foo')
        response = client.post('/control/event/dummy/dummy/orders/FOO/checkvatid', {}, follow=True)
        assert 'alert-success' in response.rendered_content
        ia.refresh_from_db()
        assert ia.vat_id_validated


@pytest.mark.django_db
def test_check_vatid_no_entered(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    ia = InvoiceAddress.objects.create(order=env[2], is_business=True, country=Country('AT'))
    with mock.patch('vat_moss.id.validate') as mock_validate:
        mock_validate.return_value = ('AT', 'AT123456', 'Foo')
        response = client.post('/control/event/dummy/dummy/orders/FOO/checkvatid', {}, follow=True)
        assert 'alert-danger' in response.rendered_content
        ia.refresh_from_db()
        assert not ia.vat_id_validated


@pytest.mark.django_db
def test_check_vatid_invalid_country(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    ia = InvoiceAddress.objects.create(order=env[2], is_business=True, vat_id='ATU1234567', country=Country('FR'))
    with mock.patch('vat_moss.id.validate') as mock_validate:
        mock_validate.return_value = ('AT', 'AT123456', 'Foo')
        response = client.post('/control/event/dummy/dummy/orders/FOO/checkvatid', {}, follow=True)
        assert 'alert-danger' in response.rendered_content
        ia.refresh_from_db()
        assert not ia.vat_id_validated


@pytest.mark.django_db
def test_check_vatid_noneu_country(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    ia = InvoiceAddress.objects.create(order=env[2], is_business=True, vat_id='CHU1234567', country=Country('CH'))
    with mock.patch('vat_moss.id.validate') as mock_validate:
        mock_validate.return_value = ('AT', 'AT123456', 'Foo')
        response = client.post('/control/event/dummy/dummy/orders/FOO/checkvatid', {}, follow=True)
        assert 'alert-danger' in response.rendered_content
        ia.refresh_from_db()
        assert not ia.vat_id_validated


@pytest.mark.django_db
def test_check_vatid_no_country(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    ia = InvoiceAddress.objects.create(order=env[2], is_business=True, vat_id='ATU1234567')
    with mock.patch('vat_moss.id.validate') as mock_validate:
        mock_validate.return_value = ('AT', 'AT123456', 'Foo')
        response = client.post('/control/event/dummy/dummy/orders/FOO/checkvatid', {}, follow=True)
        assert 'alert-danger' in response.rendered_content
        ia.refresh_from_db()
        assert not ia.vat_id_validated


@pytest.mark.django_db
def test_check_vatid_no_invoiceaddress(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with mock.patch('vat_moss.id.validate') as mock_validate:
        mock_validate.return_value = ('AT', 'AT123456', 'Foo')
        response = client.post('/control/event/dummy/dummy/orders/FOO/checkvatid', {}, follow=True)
        assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_check_vatid_invalid(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    ia = InvoiceAddress.objects.create(order=env[2], is_business=True, vat_id='ATU1234567', country=Country('AT'))
    with mock.patch('vat_moss.id.validate') as mock_validate:
        def raiser(*args, **kwargs):
            import vat_moss.errors
            raise vat_moss.errors.InvalidError('Fail')

        mock_validate.side_effect = raiser
        response = client.post('/control/event/dummy/dummy/orders/FOO/checkvatid', {}, follow=True)
        assert 'alert-danger' in response.rendered_content
        ia.refresh_from_db()
        assert not ia.vat_id_validated


@pytest.mark.django_db
def test_check_vatid_unavailable(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    ia = InvoiceAddress.objects.create(order=env[2], is_business=True, vat_id='ATU1234567', country=Country('AT'))
    with mock.patch('vat_moss.id.validate') as mock_validate:
        def raiser(*args, **kwargs):
            import vat_moss.errors
            raise vat_moss.errors.WebServiceUnavailableError('Fail')

        mock_validate.side_effect = raiser
        response = client.post('/control/event/dummy/dummy/orders/FOO/checkvatid', {}, follow=True)
        assert 'alert-danger' in response.rendered_content
        ia.refresh_from_db()
        assert not ia.vat_id_validated


@pytest.mark.django_db
def test_cancel_payment(client, env):
    p = env[2].payments.last()
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/payments/{}/cancel'.format(p.pk), {}, follow=True)
    assert 'alert-success' in response.rendered_content
    p.refresh_from_db()
    assert p.state == OrderPayment.PAYMENT_STATE_CANCELED
    response = client.post('/control/event/dummy/dummy/orders/FOO/payments/{}/cancel'.format(p.pk), {}, follow=True)
    assert 'alert-danger' in response.rendered_content


@pytest.mark.django_db
def test_cancel_refund(client, env):
    r = env[2].refunds.create(
        provider='stripe',
        state='transit',
        source='admin',
        amount=Decimal('23.00'),
        execution_date=now(),
    )
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/refunds/{}/cancel'.format(r.pk), {}, follow=True)
    assert 'alert-success' in response.rendered_content
    r.refresh_from_db()
    assert r.state == OrderRefund.REFUND_STATE_CANCELED
    r.state = OrderRefund.REFUND_STATE_DONE
    r.save()
    response = client.post('/control/event/dummy/dummy/orders/FOO/refunds/{}/cancel'.format(r.pk), {}, follow=True)
    assert 'alert-danger' in response.rendered_content
    r.refresh_from_db()
    assert r.state == OrderRefund.REFUND_STATE_DONE


@pytest.mark.django_db
def test_process_refund(client, env):
    r = env[2].refunds.create(
        provider='stripe',
        state='external',
        source='external',
        amount=Decimal('23.00'),
        execution_date=now(),
    )
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/refunds/{}/process'.format(r.pk), {}, follow=True)
    assert 'alert-success' in response.rendered_content
    r.refresh_from_db()
    assert r.state == OrderRefund.REFUND_STATE_DONE
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_process_refund_invalid_state(client, env):
    r = env[2].refunds.create(
        provider='stripe',
        state='canceled',
        source='external',
        amount=Decimal('23.00'),
        execution_date=now(),
    )
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/refunds/{}/process'.format(r.pk), {}, follow=True)
    assert 'alert-danger' in response.rendered_content
    r.refresh_from_db()
    assert r.state == OrderRefund.REFUND_STATE_CANCELED


@pytest.mark.django_db
def test_process_refund_mark_refunded(client, env):
    r = env[2].refunds.create(
        provider='stripe',
        state='external',
        source='external',
        amount=Decimal('23.00'),
        execution_date=now(),
    )
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/refunds/{}/process'.format(r.pk), {'action': 'r'},
                           follow=True)
    assert 'alert-success' in response.rendered_content
    r.refresh_from_db()
    assert r.state == OrderRefund.REFUND_STATE_DONE
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_REFUNDED


@pytest.mark.django_db
def test_done_refund(client, env):
    r = env[2].refunds.create(
        provider='stripe',
        state='transit',
        source='admin',
        amount=Decimal('23.00'),
        execution_date=now(),
    )
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/refunds/{}/done'.format(r.pk), {}, follow=True)
    assert 'alert-success' in response.rendered_content
    r.refresh_from_db()
    assert r.state == OrderRefund.REFUND_STATE_DONE


@pytest.mark.django_db
def test_done_refund_invalid_state(client, env):
    r = env[2].refunds.create(
        provider='stripe',
        state='external',
        source='external',
        amount=Decimal('23.00'),
        execution_date=now(),
    )
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/refunds/{}/done'.format(r.pk), {}, follow=True)
    assert 'alert-danger' in response.rendered_content
    r.refresh_from_db()
    assert r.state == OrderRefund.REFUND_STATE_EXTERNAL


@pytest.mark.django_db
def test_confirm_payment(client, env):
    p = env[2].payments.last()
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/payments/{}/confirm'.format(p.pk), {}, follow=True)
    assert 'alert-success' in response.rendered_content
    p.refresh_from_db()
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_confirm_payment_invalid_state(client, env):
    p = env[2].payments.last()
    p.state = OrderPayment.PAYMENT_STATE_FAILED
    p.save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/payments/{}/confirm'.format(p.pk), {}, follow=True)
    assert 'alert-danger' in response.rendered_content
    p.refresh_from_db()
    assert p.state == OrderPayment.PAYMENT_STATE_FAILED
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_confirm_payment_partal_amount(client, env):
    p = env[2].payments.last()
    p.amount -= Decimal(5.00)
    p.save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post('/control/event/dummy/dummy/orders/FOO/payments/{}/confirm'.format(p.pk), {}, follow=True)
    assert 'alert-success' in response.rendered_content
    p.refresh_from_db()
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    env[2].refresh_from_db()
    assert env[2].status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_refund_paid_order_fully_mark_as_refunded(client, env):
    p = env[2].payments.last()
    p.confirm()
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/refund')
    doc = BeautifulSoup(response.content, "lxml")
    assert doc.select("input[name$=partial_amount]")[0]["value"] == "14.00"
    client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '14.00',
        'start-mode': 'full',
        'start-action': 'mark_refunded'
    }, follow=True)
    client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '14.00',
        'start-mode': 'full',
        'start-action': 'mark_refunded',
        'refund-manual': '14.00',
        'manual_state': 'done',
        'perform': 'on'
    }, follow=True)
    p.refresh_from_db()
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    env[2].refresh_from_db()
    r = env[2].refunds.last()
    assert r.provider == "manual"
    assert r.state == OrderRefund.REFUND_STATE_DONE
    assert r.amount == Decimal('14.00')
    assert env[2].status == Order.STATUS_REFUNDED


@pytest.mark.django_db
def test_refund_paid_order_fully_mark_as_pending(client, env):
    p = env[2].payments.last()
    p.confirm()
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/refund')
    doc = BeautifulSoup(response.content, "lxml")
    assert doc.select("input[name$=partial_amount]")[0]["value"] == "14.00"
    client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '14.00',
        'start-mode': 'full',
        'start-action': 'mark_pending',
        'refund-manual': '14.00',
        'manual_state': 'pending',
        'perform': 'on'
    }, follow=True)
    p.refresh_from_db()
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    env[2].refresh_from_db()
    r = env[2].refunds.last()
    assert r.provider == "manual"
    assert r.state == OrderRefund.REFUND_STATE_CREATED
    assert r.amount == Decimal('14.00')
    assert env[2].status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_refund_paid_order_partially_mark_as_pending(client, env):
    p = env[2].payments.last()
    p.confirm()
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/FOO/refund')
    doc = BeautifulSoup(response.content, "lxml")
    assert doc.select("input[name$=partial_amount]")[0]["value"] == "14.00"
    client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '7.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending'
    }, follow=True)
    client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '7.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending',
        'refund-manual': '7.00',
        'manual_state': 'pending',
        'perform': 'on'
    }, follow=True)
    p.refresh_from_db()
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    env[2].refresh_from_db()
    r = env[2].refunds.last()
    assert r.provider == "manual"
    assert r.state == OrderRefund.REFUND_STATE_CREATED
    assert r.amount == Decimal('7.00')
    assert env[2].status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_refund_propose_lower_payment(client, env):
    p = env[2].payments.last()
    p.amount = Decimal('8.00')
    p.confirm()
    p2 = env[2].payments.create(
        amount=Decimal('6.00'), provider='stripe', state=OrderPayment.PAYMENT_STATE_CONFIRMED
    )
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.get('/control/event/dummy/dummy/orders/FOO/refund')
    response = client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '7.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending'
    }, follow=True)
    doc = BeautifulSoup(response.content, "lxml")
    assert doc.select("input[name=refund-{}]".format(p2.pk))[0]['value'] == '6.00'
    assert doc.select("input[name=refund-manual]".format(p2.pk))[0]['value'] == '1.00'


@pytest.mark.django_db
def test_refund_propose_equal_payment(client, env):
    p = env[2].payments.last()
    p.amount = Decimal('7.00')
    p.confirm()
    p2 = env[2].payments.create(
        amount=Decimal('7.00'), provider='stripe', state=OrderPayment.PAYMENT_STATE_CONFIRMED
    )
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.get('/control/event/dummy/dummy/orders/FOO/refund')
    response = client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '7.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending'
    }, follow=True)
    doc = BeautifulSoup(response.content, "lxml")
    assert doc.select("input[name=refund-{}]".format(p2.pk))[0]['value'] == '7.00'
    assert doc.select("input[name=refund-manual]".format(p2.pk))[0]['value'] == '0.00'


@pytest.mark.django_db
def test_refund_propose_higher_payment(client, env):
    p = env[2].payments.last()
    p.amount = Decimal('6.00')
    p.confirm()
    p2 = env[2].payments.create(
        amount=Decimal('8.00'), provider='stripe', state=OrderPayment.PAYMENT_STATE_CONFIRMED
    )
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.get('/control/event/dummy/dummy/orders/FOO/refund')
    response = client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '7.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending'
    }, follow=True)
    doc = BeautifulSoup(response.content, "lxml")
    assert doc.select("input[name=refund-{}]".format(p2.pk))[0]['value'] == '7.00'
    assert doc.select("input[name=refund-manual]".format(p2.pk))[0]['value'] == '0.00'


@pytest.mark.django_db
def test_refund_amount_does_not_match_or_invalid(client, env):
    p = env[2].payments.last()
    p.confirm()
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '7.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending',
        'refund-manual': '4.00',
        'refund-{}'.format(p.pk): '4.00',
        'manual_state': 'pending',
        'perform': 'on'
    }, follow=True)
    assert b'alert-danger' in resp.content
    assert b'do not match the' in resp.content
    resp = client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '15.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending',
        'refund-manual': '0.00',
        'refund-{}'.format(p.pk): '15.00',
        'manual_state': 'pending',
        'perform': 'on'
    }, follow=True)
    assert b'alert-danger' in resp.content
    assert b'The refund amount needs to be positive' in resp.content
    resp = client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '7.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending',
        'refund-manual': '-3.00',
        'refund-{}'.format(p.pk): '10.00',
        'manual_state': 'pending',
        'perform': 'on'
    }, follow=True)
    assert b'alert-danger' in resp.content
    assert b'do not match the' in resp.content
    resp = client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '7.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending',
        'refund-manual': 'AA',
        'refund-{}'.format(p.pk): '10.00',
        'manual_state': 'pending',
        'perform': 'on'
    }, follow=True)
    assert b'alert-danger' in resp.content
    assert b'invalid number' in resp.content


@pytest.mark.django_db
def test_refund_paid_order_automatically_failed(client, env, monkeypatch):
    p = env[2].payments.last()
    p.provider = 'stripe'
    p.info_data = {
        'id': 'foo'
    }
    p.confirm()
    client.login(email='dummy@dummy.dummy', password='dummy')

    def charge_retr(*args, **kwargs):
        def refund_create(amount):
            raise PaymentException('This failed.')

        c = MockedCharge()
        c.refunds.create = refund_create
        return c

    monkeypatch.setattr("stripe.Charge.retrieve", charge_retr)

    r = client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '7.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending',
        'refund-{}'.format(p.pk): '7.00',
        'manual_state': 'pending',
        'perform': 'on'
    }, follow=True)
    assert b'This failed.' in r.content
    p.refresh_from_db()
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    env[2].refresh_from_db()
    r = env[2].refunds.last()
    assert r.provider == "stripe"
    assert r.state == OrderRefund.REFUND_STATE_FAILED
    assert r.amount == Decimal('7.00')
    assert env[2].status == Order.STATUS_PAID


@pytest.mark.django_db
def test_refund_paid_order_automatically(client, env, monkeypatch):
    p = env[2].payments.last()
    p.provider = 'stripe'
    p.info_data = {
        'id': 'foo'
    }
    p.confirm()
    client.login(email='dummy@dummy.dummy', password='dummy')

    def charge_retr(*args, **kwargs):
        def refund_create(amount):
            r = MockedCharge()
            r.id = 'foo'
            r.status = 'succeeded'
            return r

        c = MockedCharge()
        c.refunds.create = refund_create
        return c

    monkeypatch.setattr("stripe.Charge.retrieve", charge_retr)

    client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '7.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending',
        'refund-{}'.format(p.pk): '7.00',
        'manual_state': 'pending',
        'perform': 'on'
    }, follow=True)
    p.refresh_from_db()
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    env[2].refresh_from_db()
    r = env[2].refunds.last()
    assert r.provider == "stripe"
    assert r.state == OrderRefund.REFUND_STATE_DONE
    assert r.amount == Decimal('7.00')
    assert env[2].status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_refund_paid_order_offsetting_to_unknown(client, env):
    p = env[2].payments.last()
    p.confirm()
    client.login(email='dummy@dummy.dummy', password='dummy')

    r = client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '5.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending',
        'refund-offsetting': '5.00',
        'order-offsetting': 'BAZ',
        'manual_state': 'pending',
        'perform': 'on'
    }, follow=True)
    assert b'alert-danger' in r.content


@pytest.mark.django_db
def test_refund_paid_order_offsetting(client, env):
    p = env[2].payments.last()
    p.confirm()
    client.login(email='dummy@dummy.dummy', password='dummy')
    o = Order.objects.create(
        code='BAZ', event=env[0], email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=5, locale='en'
    )

    client.post('/control/event/dummy/dummy/orders/FOO/refund', {
        'start-partial_amount': '5.00',
        'start-mode': 'partial',
        'start-action': 'mark_pending',
        'refund-offsetting': '5.00',
        'order-offsetting': 'BAZ',
        'manual_state': 'pending',
        'perform': 'on'
    }, follow=True)
    p.refresh_from_db()
    assert p.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    env[2].refresh_from_db()
    r = env[2].refunds.last()
    assert r.provider == "offsetting"
    assert r.state == OrderRefund.REFUND_STATE_DONE
    assert r.amount == Decimal('5.00')
    assert env[2].status == Order.STATUS_PENDING
    o.refresh_from_db()
    assert o.status == Order.STATUS_PAID
    p2 = o.payments.first()
    assert p2.provider == "offsetting"
    assert p2.amount == Decimal('5.00')
    assert p2.state == OrderPayment.PAYMENT_STATE_CONFIRMED


@pytest.mark.django_db
def test_refund_list(client, env):
    env[2].refunds.create(
        provider='banktransfer',
        state='done',
        source='admin',
        amount=Decimal('23.00'),
        execution_date=now(),
    )
    env[2].refunds.create(
        provider='manual',
        state='created',
        source='admin',
        amount=Decimal('23.00'),
        execution_date=now(),
    )
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/refunds/')
    assert 'R-1' not in response.rendered_content
    assert 'R-2' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/refunds/?status=all')
    assert 'R-1' in response.rendered_content
    assert 'R-2' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/refunds/?status=created')
    assert 'R-1' not in response.rendered_content
    assert 'R-2' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/refunds/?status=done')
    assert 'R-1' in response.rendered_content
    assert 'R-2' not in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/refunds/?status=all&provider=manual')
    assert 'R-1' not in response.rendered_content
    assert 'R-2' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/refunds/?status=all&provider=banktransfer')
    assert 'R-1' in response.rendered_content
    assert 'R-2' not in response.rendered_content
