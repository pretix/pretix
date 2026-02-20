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
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Event, Order, Organizer
from pretix.base.models.orders import (
    InstallmentPlan, OrderPayment, ScheduledInstallment,
)
from pretix.base.payment import PaymentException


class TestInstallmentRecovery(TestCase):

    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='Dummy', slug='dummy')
        self.orga.settings.customer_accounts = False
        self.event = Event.objects.create(
            organizer=self.orga, name='Dummy Event', slug='dummy',
            date_from=now(), live=True,
        )
        self.order = Order.objects.create(
            code='ABCDE', event=self.event, email='test@example.com',
            status=Order.STATUS_PENDING, datetime=now(),
            expires=now() + timedelta(days=10), total=Decimal('300.00'),
            locale='en',
            sales_channel=self.orga.sales_channels.get(identifier="web"),
            customer=None,
        )
        self.plan = InstallmentPlan.objects.create(
            order=self.order, payment_provider='dummy',
            payment_token={'token': 'tok_123'}, total_installments=3,
            installments_paid=1, amount_per_installment=Decimal('100.00'),
            status=InstallmentPlan.STATUS_ACTIVE,
            grace_period_end=now() + timedelta(days=5),
        )
        self.installment = ScheduledInstallment.objects.create(
            plan=self.plan, installment_number=2, amount=Decimal('100.00'),
            due_date=now() - timedelta(days=2), state=ScheduledInstallment.STATE_FAILED,
        )

    def _url(self):
        return f'/{self.orga.slug}/{self.event.slug}/order/{self.order.code}/{self.order.secret}/installment-recovery/'

    def _mock_provider(self, **overrides):
        defaults = {
            'installments_supported': True,
            'checkout_prepare': True,
            'execute_payment': None,
            'payment_form_render': '<form></form>',
        }
        defaults.update(overrides)
        provider = MagicMock()
        provider.installments_supported = defaults['installments_supported']
        provider.checkout_prepare.return_value = defaults['checkout_prepare']
        provider.execute_payment.return_value = defaults['execute_payment']
        provider.payment_form_render.return_value = defaults['payment_form_render']
        return provider

    # -- Dispatch / access control --

    @scopes_disabled()
    def test_404_without_plan(self):
        self.plan.delete()
        assert self.client.get(self._url()).status_code == 404

    @scopes_disabled()
    def test_404_without_failed_installment(self):
        self.installment.state = ScheduledInstallment.STATE_PAID
        self.installment.save()
        assert self.client.get(self._url()).status_code == 404

    def test_404_with_wrong_secret(self):
        url = f'/{self.orga.slug}/{self.event.slug}/order/{self.order.code}/WRONGSECRET/installment-recovery/'
        assert self.client.get(url).status_code == 404

    @scopes_disabled()
    def test_selects_earliest_failed_installment(self):
        ScheduledInstallment.objects.create(
            plan=self.plan, installment_number=3, amount=Decimal('100.00'),
            due_date=now() + timedelta(days=5), state=ScheduledInstallment.STATE_FAILED,
        )
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': self._mock_provider()}):
            response = self.client.get(self._url())
        assert response.status_code == 200
        assert response.context['failed_installment'].pk == self.installment.pk

    # -- GET rendering --

    def test_get_renders_200(self):
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': self._mock_provider()}):
            assert self.client.get(self._url()).status_code == 200

    def test_get_shows_payment_form(self):
        provider = self._mock_provider(payment_form_render='<form>test</form>')
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': provider}):
            response = self.client.get(self._url())
        assert response.context['payment_form_html'] == '<form>test</form>'

    def test_get_error_when_provider_missing(self):
        with patch('pretix.base.models.Event.get_payment_providers', return_value={}):
            response = self.client.get(self._url())
        assert response.status_code == 200
        assert 'payment_form_error' in response.context

    def test_get_error_when_installments_not_supported(self):
        provider = self._mock_provider(installments_supported=False)
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': provider}):
            response = self.client.get(self._url())
        assert response.status_code == 200
        assert 'payment_form_error' in response.context

    def test_get_error_when_render_raises(self):
        provider = self._mock_provider()
        provider.payment_form_render.side_effect = Exception('render error')
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': provider}):
            response = self.client.get(self._url())
        assert response.status_code == 200
        assert 'payment_form_error' in response.context

    # -- POST success --

    @scopes_disabled()
    def test_post_success(self):
        provider = self._mock_provider()
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': provider}):
            response = self.client.post(self._url())

        assert response.status_code == 302
        assert self.order.code in response.url

        payment = OrderPayment.objects.get(order=self.order)
        assert payment.provider == 'dummy'
        assert payment.amount == Decimal('100.00')
        assert payment.installment_plan == self.plan
        assert payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED

        self.installment.refresh_from_db()
        assert self.installment.state == ScheduledInstallment.STATE_PAID
        assert self.installment.payment == payment

        self.plan.refresh_from_db()
        assert self.plan.installments_paid == 2
        assert self.plan.grace_period_end is None
        assert self.plan.grace_warning_sent is False

    @scopes_disabled()
    def test_post_completes_plan_on_last_installment(self):
        self.plan.installments_paid = 2
        self.plan.save(update_fields=['installments_paid'])

        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': self._mock_provider()}):
            self.client.post(self._url())

        self.plan.refresh_from_db()
        assert self.plan.status == InstallmentPlan.STATUS_COMPLETED

    @scopes_disabled()
    def test_post_does_not_complete_plan_when_not_last(self):
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': self._mock_provider()}):
            self.client.post(self._url())

        self.plan.refresh_from_db()
        assert self.plan.status == InstallmentPlan.STATUS_ACTIVE

    @scopes_disabled()
    def test_post_only_recovers_first_failed_installment(self):
        second_failed = ScheduledInstallment.objects.create(
            plan=self.plan, installment_number=3, amount=Decimal('100.00'),
            due_date=now() + timedelta(days=5), state=ScheduledInstallment.STATE_FAILED,
        )
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': self._mock_provider()}):
            self.client.post(self._url())

        self.installment.refresh_from_db()
        second_failed.refresh_from_db()
        assert self.installment.state == ScheduledInstallment.STATE_PAID
        assert second_failed.state == ScheduledInstallment.STATE_FAILED

    # -- POST failure paths --

    def test_post_provider_unavailable_redirects(self):
        with patch('pretix.base.models.Event.get_payment_providers', return_value={}):
            assert self.client.post(self._url()).status_code == 302

    def test_post_installments_not_supported_redirects(self):
        provider = self._mock_provider(installments_supported=False)
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': provider}):
            assert self.client.post(self._url()).status_code == 302

    @scopes_disabled()
    def test_post_checkout_prepare_false_rerenders(self):
        provider = self._mock_provider(checkout_prepare=False)
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': provider}):
            response = self.client.post(self._url())
        assert response.status_code == 200
        assert not OrderPayment.objects.filter(order=self.order).exists()

    def test_post_checkout_prepare_returns_url_redirects(self):
        provider = self._mock_provider(checkout_prepare='https://pay.example.com/')
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': provider}):
            response = self.client.post(self._url())
        assert response.status_code == 302
        assert response.url == 'https://pay.example.com/'

    @scopes_disabled()
    def test_post_payment_exception_marks_failed(self):
        provider = self._mock_provider()
        provider.execute_payment.side_effect = PaymentException('Card declined')
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': provider}):
            response = self.client.post(self._url())

        assert response.status_code == 302
        payment = OrderPayment.objects.get(order=self.order)
        assert payment.state == OrderPayment.PAYMENT_STATE_FAILED
        self.installment.refresh_from_db()
        assert self.installment.state == ScheduledInstallment.STATE_FAILED

    def test_post_execute_payment_returns_url_redirects(self):
        provider = self._mock_provider(execute_payment='https://confirm.example.com/')
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': provider}):
            response = self.client.post(self._url())
        assert response.status_code == 302
        assert response.url == 'https://confirm.example.com/'

    def test_post_unexpected_exception_rerenders(self):
        provider = self._mock_provider()
        provider.execute_payment.side_effect = RuntimeError('unexpected')
        with patch('pretix.base.models.Event.get_payment_providers', return_value={'dummy': provider}):
            assert self.client.post(self._url()).status_code == 200
