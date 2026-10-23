#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import Event, Order, OrderPayment, Organizer
from pretix.plugins.stripe.payment import StripePix


class MockedCharge:
    status = 'succeeded'
    paid = True
    id = 'ch_pix123'


class MockedPaymentIntent:
    status = 'succeeded'
    id = 'pi_pix123'
    latest_charge = MockedCharge()
    last_payment_error = None

    def __str__(self):
        return json.dumps({
            'id': self.id,
            'status': self.status,
            'paid': True,
        })


class MockedPixNextAction:
    type = 'pix_display_qr_code'
    pix_display_qr_code = {
        'hosted_instructions_url': 'https://hooks.stripe.com/pix/test_instructions',
    }


class MockedRequiresActionIntent:
    status = 'requires_action'
    id = 'pi_pix123'
    next_action = MockedPixNextAction()


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    with scope(organizer=o):
        event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(), live=True, currency='BRL',
            plugins='pretix.plugins.stripe'
        )
        event.settings.set('payment_stripe__enabled', True)
        event.settings.set('payment_stripe_method_pix', True)
        event.settings.set('payment_stripe_secret_key', 'sk_test_123')
        order = Order.objects.create(
            code='FOOBAR', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now() + timedelta(days=3),
            total=Decimal('13.37'),
            sales_channel=o.sales_channels.get(identifier="web"),
        )
        payment = order.payments.create(
            amount=Decimal('13.37'),
            state=OrderPayment.PAYMENT_STATE_CREATED,
            provider='stripe_pix',
        )
        yield event, order, payment


@pytest.fixture
def factory():
    return RequestFactory()


class FakeSession(dict):
    """A minimal stand-in for Django's session store."""
    session_key = None

    def create(self):
        self.session_key = 'pixtestsess10n'


def _request(factory, session=None):
    request = factory.get('/')
    request.session = FakeSession(session or {})
    return request


@pytest.mark.django_db
def test_registered_as_payment_provider():
    from pretix.plugins.stripe.signals import register_payment_provider
    assert StripePix in register_payment_provider(None)


@pytest.mark.django_db
def test_is_allowed_requires_brl(env, factory):
    event, order, payment = env
    prov = StripePix(event)
    request = _request(factory)
    request.event = event
    assert prov.is_allowed(request, Decimal('13.37'))
    event.currency = 'EUR'
    assert not prov.is_allowed(request, Decimal('13.37'))


@pytest.mark.django_db
def test_payment_intent_kwargs(env, factory):
    event, order, payment = env
    prov = StripePix(event)
    request = _request(factory, {
        'payment_stripe_pix_name': 'Maria Silva',
        'payment_stripe_pix_tax_id': '123.456.789-09',
    })
    kwargs = prov._payment_intent_kwargs(request, payment)
    assert kwargs['payment_method_data'] == {
        'type': 'pix',
        'billing_details': {
            'name': 'Maria Silva',
            'email': 'dummy@dummy.test',
            'tax_id': '12345678909',
        },
    }
    expires = kwargs['payment_method_options']['pix']['expires_after_seconds']
    # Order expires in ~3 days, Stripe allows at most 14 days
    assert 3 * 24 * 60 * 60 - 60 <= expires <= 3 * 24 * 60 * 60


@pytest.mark.django_db
def test_payment_intent_kwargs_caps_expiry_at_14_days(env, factory):
    event, order, payment = env
    order.expires = now() + timedelta(days=30)
    order.save()
    prov = StripePix(event)
    request = _request(factory, {'payment_stripe_pix_name': 'Maria Silva'})
    kwargs = prov._payment_intent_kwargs(request, payment)
    assert kwargs['payment_method_options']['pix']['expires_after_seconds'] == 14 * 24 * 60 * 60


@pytest.mark.django_db
def test_payment_intent_kwargs_without_expiry_option(env, factory):
    event, order, payment = env
    order.expires = now() + timedelta(seconds=30)
    order.save()
    prov = StripePix(event)
    request = _request(factory, {'payment_stripe_pix_name': 'Maria Silva'})
    kwargs = prov._payment_intent_kwargs(request, payment)
    # Stripe requires at least 60 seconds, so we don't send the option at all for
    # orders that are about to expire anyway
    assert 'payment_method_options' not in kwargs


@pytest.mark.django_db
def test_payment_intent_kwargs_fallbacks(env, factory):
    event, order, payment = env
    prov = StripePix(event)
    request = _request(factory)
    kwargs = prov._payment_intent_kwargs(request, payment)
    billing = kwargs['payment_method_data']['billing_details']
    assert billing['name'] == 'unknown name'
    assert billing['email'] == 'dummy@dummy.test'
    assert 'tax_id' not in billing


@pytest.mark.django_db
def test_checkout_prepare_valid(env, factory):
    event, order, payment = env
    prov = StripePix(event)
    request = factory.post('/', {
        'payment': 'stripe_pix',
        'payment_stripe_pix-name': 'Maria Silva',
        'payment_stripe_pix-tax_id': '123.456.789-09',
    })
    request.session = FakeSession()
    request.event = event
    assert prov.checkout_prepare(request, {}) is True
    assert request.session['payment_stripe_pix_payment_method_id'] is None
    assert request.session['payment_stripe_pix_name'] == 'Maria Silva'
    assert request.session['payment_stripe_pix_tax_id'] == '123.456.789-09'


@pytest.mark.django_db
def test_checkout_prepare_invalid(env, factory):
    event, order, payment = env
    prov = StripePix(event)
    request = factory.post('/', {
        'payment': 'stripe_pix',
        'payment_stripe_pix-tax_id': '123.456.789-09',
    })
    request.session = FakeSession()
    request.event = event
    assert prov.checkout_prepare(request, {}) is False
    assert 'payment_stripe_pix_name' not in request.session


@pytest.mark.django_db
def test_payment_form_render(env, factory):
    event, order, payment = env
    prov = StripePix(event)
    request = _request(factory)
    request.event = event
    rendered = prov.payment_form_render(request)
    assert 'payment_stripe_pix-name' in rendered
    assert 'payment_stripe_pix-tax_id' in rendered
    assert 'Pix' in rendered


@pytest.mark.django_db
def test_execute_payment_confirms_and_cleans_session(env, factory, monkeypatch):
    event, order, payment = env

    def paymentintent_create(**kwargs):
        assert kwargs['amount'] == 1337
        assert kwargs['currency'] == 'brl'
        assert kwargs['payment_method_types'] == ['pix']
        assert kwargs['confirmation_method'] == 'automatic'
        assert kwargs['payment_method_data']['billing_details']['email'] == 'dummy@dummy.test'
        assert kwargs['payment_method_options']['pix']['expires_after_seconds'] > 60
        return MockedPaymentIntent()

    monkeypatch.setattr("stripe.PaymentIntent.create", paymentintent_create)

    prov = StripePix(event)
    request = _request(factory, {
        'payment_stripe_pix_payment_method_id': None,
        'payment_stripe_pix_name': 'Maria Silva',
        'payment_stripe_pix_tax_id': '123.456.789-09',
    })
    request.event = event

    prov.execute_payment(request, payment)

    order.refresh_from_db()
    payment.refresh_from_db()
    assert order.status == Order.STATUS_PAID
    assert payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    # Session is cleaned up after the payment attempt
    assert 'payment_stripe_pix_name' not in request.session
    assert 'payment_stripe_pix_tax_id' not in request.session
    assert 'payment_stripe_pix_payment_method_id' not in request.session


@pytest.mark.django_db
def test_sca_view_shows_pix_instructions(env, client, monkeypatch):
    from pretix.multidomain.urlreverse import eventreverse

    event, order, payment = env
    payment.info = json.dumps({'id': 'pi_pix123'})
    payment.state = OrderPayment.PAYMENT_STATE_CREATED
    payment.save()

    monkeypatch.setattr(
        "stripe.PaymentIntent.retrieve",
        lambda *args, **kwargs: MockedRequiresActionIntent()
    )

    url = eventreverse(event, 'plugins:stripe:sca', kwargs={
        'order': order.code,
        'hash': order.tagged_secret('plugins:stripe'),
        'payment': payment.pk,
    })
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert 'https://hooks.stripe.com/pix/test_instructions' in content
    assert 'iframe' in content
