import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.utils.timezone import now
from stripe import APIConnectionError, CardError, StripeError

from pretix.base.models import Event, Order, Organizer
from pretix.base.payment import PaymentException
from pretix.plugins.stripe.payment import StripeCC


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), live=True
    )
    o1 = Order.objects.create(
        code='FOOBAR', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=Decimal('13.37'), payment_provider='banktransfer'
    )
    return event, o1


@pytest.fixture(autouse=True)
def no_messages(monkeypatch):
    # Patch out template rendering for performance improvements
    monkeypatch.setattr("django.contrib.messages.api.add_message", lambda *args, **kwargs: None)


@pytest.fixture
def factory():
    return RequestFactory()


class MockedCharge():
    def __init__(self):
        self.status = ''
        self.paid = False
        self.id = 'ch_123345345'

    def refresh(self):
        pass


@pytest.mark.django_db
def test_perform_success(env, factory, monkeypatch):
    event, order = env

    def charge_create(**kwargs):
        assert kwargs['amount'] == 1337
        assert kwargs['currency'] == 'eur'
        assert kwargs['source'] == 'tok_189fTT2eZvKYlo2CvJKzEzeu'
        c = MockedCharge()
        c.status = 'succeeded'
        c.paid = True
        return c

    monkeypatch.setattr("stripe.Charge.create", charge_create)
    prov = StripeCC(event)
    req = factory.post('/', {
        'stripe_token': 'tok_189fTT2eZvKYlo2CvJKzEzeu',
        'stripe_last4': '4242',
        'stripe_brand': 'Visa'
    })
    req.session = {}
    prov.checkout_prepare(req, {})
    assert 'payment_stripe_token' in req.session
    prov.payment_perform(req, order)
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_perform_card_error(env, factory, monkeypatch):
    event, order = env

    def charge_create(**kwargs):
        raise CardError(message='Foo', param='foo', code=100)

    monkeypatch.setattr("stripe.Charge.create", charge_create)
    prov = StripeCC(event)
    req = factory.post('/', {
        'stripe_token': 'tok_189fTT2eZvKYlo2CvJKzEzeu',
        'stripe_last4': '4242',
        'stripe_brand': 'Visa'
    })
    req.session = {}
    prov.checkout_prepare(req, {})
    assert 'payment_stripe_token' in req.session
    with pytest.raises(PaymentException):
        prov.payment_perform(req, order)
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_perform_stripe_error(env, factory, monkeypatch):
    event, order = env

    def charge_create(**kwargs):
        raise StripeError(message='Foo')

    monkeypatch.setattr("stripe.Charge.create", charge_create)
    prov = StripeCC(event)
    req = factory.post('/', {
        'stripe_token': 'tok_189fTT2eZvKYlo2CvJKzEzeu',
        'stripe_last4': '4242',
        'stripe_brand': 'Visa'
    })
    req.session = {}
    prov.checkout_prepare(req, {})
    assert 'payment_stripe_token' in req.session
    with pytest.raises(PaymentException):
        prov.payment_perform(req, order)
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_perform_failed(env, factory, monkeypatch):
    event, order = env

    def charge_create(**kwargs):
        c = MockedCharge()
        c.status = 'failed'
        c.paid = True
        c.failure_message = 'Foo'
        return c

    monkeypatch.setattr("stripe.Charge.create", charge_create)
    prov = StripeCC(event)
    req = factory.post('/', {
        'stripe_token': 'tok_189fTT2eZvKYlo2CvJKzEzeu',
        'stripe_last4': '4242',
        'stripe_brand': 'Visa'
    })
    req.session = {}
    prov.checkout_prepare(req, {})
    assert 'payment_stripe_token' in req.session
    with pytest.raises(PaymentException):
        prov.payment_perform(req, order)
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_refund_success(env, factory, monkeypatch):
    event, order = env

    def charge_retr(*args, **kwargs):
        def refund_create():
            pass

        c = MockedCharge()
        c.refunds = MockedCharge()
        c.refunds.create = refund_create
        return c

    monkeypatch.setattr("stripe.Charge.retrieve", charge_retr)
    order.status = Order.STATUS_PAID
    order.payment_info = json.dumps({
        'id': 'ch_123345345'
    })
    order.save()
    prov = StripeCC(event)
    req = factory.post('/', data={'auto_refund': 'auto'})
    req.user = None
    prov.order_control_refund_perform(req, order)
    order.refresh_from_db()
    assert order.status == Order.STATUS_REFUNDED


@pytest.mark.django_db
def test_refund_unavailable(env, factory, monkeypatch):
    event, order = env

    def charge_retr(*args, **kwargs):
        def refund_create():
            raise APIConnectionError(message='Foo')

        c = MockedCharge()
        c.refunds = object()
        c.refunds.create = refund_create()
        return c

    monkeypatch.setattr("stripe.Charge.retrieve", charge_retr)
    order.status = Order.STATUS_PAID
    order.payment_info = json.dumps({
        'id': 'ch_123345345'
    })
    order.save()
    prov = StripeCC(event)
    req = factory.get('/')
    req.user = None
    prov.order_control_refund_perform(req, order)
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID
