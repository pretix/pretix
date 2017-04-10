from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.utils.timezone import now
from tests.base import SoupTest

from pretix.base.models import (
    Event, EventPermission, InvoiceAddress, Item, Order, OrderPosition,
    Organizer, Quota, User,
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
    EventPermission.objects.create(
        event=event,
        user=user,
        can_view_orders=True,
        can_change_orders=True
    )
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
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/orders/')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?user=peter')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?user=hans')
    assert 'FOO' not in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?user=dummy')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?status=p')
    assert 'FOO' not in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?status=n')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?status=ne')
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?item=15')
    assert 'FOO' not in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?item=%s' % env[3].id)
    assert 'FOO' in response.rendered_content
    response = client.get('/control/event/dummy/dummy/orders/?provider=foo')
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
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket', tax_rate=Decimal('7.00'),
                                          default_price=Decimal('23.00'), admission=True)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', tax_rate=Decimal('19.00'),
                                         default_price=Decimal('12.00'))
        self.op1 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name="Peter"
        )
        self.op2 = OrderPosition.objects.create(
            order=self.order, item=self.ticket, variation=None,
            price=Decimal("23.00"), attendee_name="Dieter"
        )
        user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        EventPermission.objects.create(
            event=self.event,
            user=user,
            can_view_orders=True,
            can_change_orders=True
        )
        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_change_item_success(self):
        self.client.post('/control/event/{}/{}/orders/{}/change'.format(
            self.event.organizer.slug, self.event.slug, self.order.code
        ), {
            'op-{}-operation'.format(self.op1.pk): 'product',
            'op-{}-itemvar'.format(self.op1.pk): str(self.shirt.pk),
            'op-{}-operation'.format(self.op2.pk): '',
            'op-{}-itemvar'.format(self.op2.pk): str(self.ticket.pk),
        })
        self.op1.refresh_from_db()
        self.order.refresh_from_db()
        assert self.op1.item == self.shirt
        assert self.op1.price == self.shirt.default_price
        assert self.op1.tax_rate == self.shirt.tax_rate
        assert self.order.total == self.op1.price + self.op2.price

    def test_change_price_success(self):
        self.client.post('/control/event/{}/{}/orders/{}/change'.format(
            self.event.organizer.slug, self.event.slug, self.order.code
        ), {
            'op-{}-operation'.format(self.op1.pk): 'price',
            'op-{}-itemvar'.format(self.op1.pk): str(self.ticket.pk),
            'op-{}-price'.format(self.op1.pk): '24.00',
            'op-{}-operation'.format(self.op2.pk): '',
            'op-{}-itemvar'.format(self.op2.pk): str(self.ticket.pk),
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
        })
        self.order.refresh_from_db()
        assert self.order.positions.count() == 1
        assert self.order.total == self.op2.price
