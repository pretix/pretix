from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.utils.timezone import now
from tests.base import SoupTest

from pretix.base.models import (
    Event, InvoiceAddress, Item, Order, OrderPosition, Organizer, Quota, Team,
    User,
)
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice,
)


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,tests.testdummy'
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
        total=14, payment_provider='banktransfer', locale='en'
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
        attendee_name="Peter"
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
@pytest.mark.parametrize("process", [
    # (Old status, new status, success expected)
    (Order.STATUS_CANCELED, Order.STATUS_PAID, False),
    (Order.STATUS_CANCELED, Order.STATUS_PENDING, False),
    (Order.STATUS_CANCELED, Order.STATUS_REFUNDED, False),
    (Order.STATUS_CANCELED, Order.STATUS_EXPIRED, False),

    (Order.STATUS_PAID, Order.STATUS_PENDING, True),
    (Order.STATUS_PAID, Order.STATUS_CANCELED, False),
    (Order.STATUS_PAID, Order.STATUS_REFUNDED, True),
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
    assert 'alert-success' in response.rendered_content
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
    assert 'alert-danger' in response.rendered_content
    o = Order.objects.get(id=env[2].id)
    assert o.expires.strftime("%Y-%m-%d %H:%M:%S") == olddate.strftime("%Y-%m-%d %H:%M:%S")
    assert o.status == Order.STATUS_EXPIRED


@pytest.mark.django_db
def test_order_extend_expired_quota_partial(client, env):
    o = Order.objects.get(id=env[2].id)
    OrderPosition.objects.create(
        order=o,
        item=env[3],
        variation=None,
        price=Decimal("14"),
        attendee_name="Peter"
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
    assert 'alert-danger' in response.rendered_content
    o = Order.objects.get(id=env[2].id)
    assert o.expires.strftime("%Y-%m-%d %H:%M:%S") == olddate.strftime("%Y-%m-%d %H:%M:%S")
    assert o.status == Order.STATUS_EXPIRED


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
            total=Decimal('46.00'), payment_provider='banktransfer'
        )
        tr7 = self.event.tax_rules.create(rate=7)
        tr19 = self.event.tax_rules.create(rate=19)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket', tax_rule=tr7,
                                          default_price=Decimal('23.00'), admission=True)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', tax_rule=tr19,
                                         default_price=Decimal('12.00'))
        self.op1 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name="Peter"
        )
        self.op2 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name="Dieter"
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
