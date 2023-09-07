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
# This file contains Apache-licensed contributions copyrighted by: Jakob Schnell
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.utils.timezone import now
from django_scopes import scope
from stripe.error import APIConnectionError, CardError

from pretix.base.models import Event, Order, OrderRefund, Organizer
from pretix.base.payment import PaymentException
from pretix.plugins.stripe.payment import StripeCC


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    with scope(organizer=o):
        event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(), live=True
        )
        o1 = Order.objects.create(
            code='FOOBAR', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now() + timedelta(days=10),
            total=Decimal('13.37')
        )
        yield event, o1


@pytest.fixture(autouse=True)
def no_messages(monkeypatch):
    # Patch out template rendering for performance improvements
    monkeypatch.setattr("django.contrib.messages.api.add_message", lambda *args, **kwargs: None)


@pytest.fixture
def factory():
    return RequestFactory()


class MockedRefunds():
    pass


class MockedCharge():
    status = ''
    paid = False
    id = 'ch_123345345'
    refunds = MockedRefunds()

    def __str__(self):
        return json.dumps({
            'id': self.id,
            'status': self.status,
            'paid': self.paid,
        })

    def refresh(self):
        pass


class Object():
    pass


class MockedPaymentintent():
    status = ''
    id = 'pi_1EUon12Tb35ankTnZyvC3SdE'
    charges = Object()
    charges.data = [MockedCharge()]
    last_payment_error = None


@pytest.mark.django_db
def test_perform_success(env, factory, monkeypatch):
    event, order = env

    def paymentintent_create(**kwargs):
        assert kwargs['amount'] == 1337
        assert kwargs['currency'] == 'eur'
        assert kwargs['payment_method'] == 'pm_189fTT2eZvKYlo2CvJKzEzeu'
        c = MockedPaymentintent()
        c.status = 'succeeded'
        c.charges.data[0].paid = True
        return c

    monkeypatch.setattr("stripe.PaymentIntent.create", paymentintent_create)

    prov = StripeCC(event)
    req = factory.post('/', {
        'stripe_card_payment_method_id': 'pm_189fTT2eZvKYlo2CvJKzEzeu',
        'stripe_card_last4': '4242',
        'stripe_card_brand': 'Visa'
    })
    req.session = {}
    prov.checkout_prepare(req, {})
    assert 'payment_stripe_card_payment_method_id' in req.session
    payment = order.payments.create(
        provider='stripe_cc', amount=order.total
    )
    prov.execute_payment(req, payment)
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_perform_success_zero_decimal_currency(env, factory, monkeypatch):
    event, order = env
    event.currency = 'JPY'
    event.save()

    def paymentintent_create(**kwargs):
        assert kwargs['amount'] == 13
        assert kwargs['currency'] == 'jpy'
        assert kwargs['payment_method'] == 'pm_189fTT2eZvKYlo2CvJKzEzeu'
        c = MockedPaymentintent()
        c.status = 'succeeded'
        c.charges.data[0].paid = True
        return c

    monkeypatch.setattr("stripe.PaymentIntent.create", paymentintent_create)
    prov = StripeCC(event)
    req = factory.post('/', {
        'stripe_card_payment_method_id': 'pm_189fTT2eZvKYlo2CvJKzEzeu',
        'stripe_card_last4': '4242',
        'stripe_card_brand': 'Visa'
    })
    req.session = {}
    prov.checkout_prepare(req, {})
    assert 'payment_stripe_card_payment_method_id' in req.session
    payment = order.payments.create(
        provider='stripe_cc', amount=order.total
    )
    prov.execute_payment(req, payment)
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID


@pytest.mark.django_db
def test_perform_card_error(env, factory, monkeypatch):
    event, order = env

    def paymentintent_create(**kwargs):
        raise CardError(message='Foo', param='foo', code=100)

    monkeypatch.setattr("stripe.PaymentIntent.create", paymentintent_create)
    prov = StripeCC(event)
    req = factory.post('/', {
        'stripe_card_payment_method_id': 'pm_189fTT2eZvKYlo2CvJKzEzeu',
        'stripe_card_last4': '4242',
        'stripe_card_brand': 'Visa'
    })
    req.session = {}
    prov.checkout_prepare(req, {})
    assert 'payment_stripe_card_payment_method_id' in req.session
    with pytest.raises(PaymentException):
        payment = order.payments.create(
            provider='stripe_cc', amount=order.total
        )
        prov.execute_payment(req, payment)
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_perform_stripe_error(env, factory, monkeypatch):
    event, order = env

    def paymentintent_create(**kwargs):
        raise CardError(message='Foo', param='foo', code=100)

    monkeypatch.setattr("stripe.PaymentIntent.create", paymentintent_create)
    prov = StripeCC(event)
    req = factory.post('/', {
        'stripe_card_payment_method_id': 'pm_189fTT2eZvKYlo2CvJKzEzeu',
        'stripe_card_last4': '4242',
        'stripe_card_brand': 'Visa'
    })
    req.session = {}
    prov.checkout_prepare(req, {})
    assert 'payment_stripe_card_payment_method_id' in req.session
    with pytest.raises(PaymentException):
        payment = order.payments.create(
            provider='stripe_cc', amount=order.total
        )
        prov.execute_payment(req, payment)
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_perform_failed(env, factory, monkeypatch):
    event, order = env

    def paymentintent_create(**kwargs):
        assert kwargs['amount'] == 1337
        assert kwargs['currency'] == 'eur'
        assert kwargs['payment_method'] == 'pm_189fTT2eZvKYlo2CvJKzEzeu'
        c = MockedPaymentintent()
        c.status = 'failed'
        c.failure_message = 'Foo'
        c.charges.data[0].paid = True
        c.last_payment_error = Object()
        c.last_payment_error.message = "Foo"
        return c

    monkeypatch.setattr("stripe.PaymentIntent.create", paymentintent_create)
    prov = StripeCC(event)
    req = factory.post('/', {
        'stripe_card_payment_method_id': 'pm_189fTT2eZvKYlo2CvJKzEzeu',
        'stripe_card_last4': '4242',
        'stripe_card_brand': 'Visa'
    })
    req.session = {}
    prov.checkout_prepare(req, {})
    assert 'payment_stripe_card_payment_method_id' in req.session
    with pytest.raises(PaymentException):
        payment = order.payments.create(
            provider='stripe_cc', amount=order.total
        )
        prov.execute_payment(req, payment)
    order.refresh_from_db()
    assert order.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_refund_success(env, factory, monkeypatch):
    event, order = env

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
    order.status = Order.STATUS_PAID
    p = order.payments.create(provider='stripe_cc', amount=order.total, info=json.dumps({
        'id': 'ch_123345345'
    }))
    order.save()
    prov = StripeCC(event)
    refund = order.refunds.create(
        provider='stripe_cc', amount=order.total, payment=p,
    )
    prov.execute_refund(refund)
    refund.refresh_from_db()
    assert refund.state == OrderRefund.REFUND_STATE_DONE


@pytest.mark.django_db
def test_refund_unavailable(env, factory, monkeypatch):
    event, order = env

    def charge_retr(*args, **kwargs):
        def refund_create(amount):
            raise APIConnectionError(message='Foo')

        c = MockedCharge()
        c.refunds.create = refund_create
        return c

    monkeypatch.setattr("stripe.Charge.retrieve", charge_retr)
    order.status = Order.STATUS_PAID
    p = order.payments.create(provider='stripe_cc', amount=order.total, info=json.dumps({
        'id': 'ch_123345345'
    }))
    order.save()
    prov = StripeCC(event)
    refund = order.refunds.create(
        provider='stripe_cc', amount=order.total, payment=p
    )
    with pytest.raises(PaymentException):
        prov.execute_refund(refund)
    refund.refresh_from_db()
    assert refund.state != OrderRefund.REFUND_STATE_DONE
