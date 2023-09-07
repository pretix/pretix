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
# This file contains Apache-licensed contributions copyrighted by: FlaviaBastos, Jakob Schnell, Tobias Kunze, luto
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import hashlib
import json
import logging
import re
import urllib.parse
from collections import OrderedDict
from decimal import Decimal

import stripe
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.db import transaction
from django.http import HttpRequest
from django.template.loader import get_template
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.safestring import mark_safe
from django.utils.timezone import now
from django.utils.translation import gettext, gettext_lazy as _, pgettext
from django_countries import countries

from pretix import __version__
from pretix.base.decimal import round_decimal
from pretix.base.forms import SecretKeySettingsField
from pretix.base.forms.questions import guess_country
from pretix.base.models import (
    Event, InvoiceAddress, Order, OrderPayment, OrderRefund, Quota,
)
from pretix.base.payment import (
    BasePaymentProvider, PaymentException, WalletQueries,
)
from pretix.base.plugins import get_all_plugins
from pretix.base.services.mail import SendMailException
from pretix.base.settings import SettingsSandbox
from pretix.helpers import OF_SELF
from pretix.helpers.countries import CachedCountries
from pretix.helpers.http import get_client_ip
from pretix.helpers.urls import build_absolute_uri as build_global_uri
from pretix.multidomain.urlreverse import build_absolute_uri, eventreverse
from pretix.plugins.stripe.forms import StripeKeyValidator
from pretix.plugins.stripe.models import (
    ReferencedStripeObject, RegisteredApplePayDomain,
)
from pretix.plugins.stripe.tasks import (
    get_stripe_account_key, stripe_verify_domain,
)
from pretix.presale.views.cart import cart_session

logger = logging.getLogger('pretix.plugins.stripe')

# State of the payment methods
#
# Source: https://stripe.com/docs/payments/payment-methods/overview
# Last Update: 2023-04-24
#
# Cards
# - Credit and Debit Cards: ✓
# - Apple, Google Pay: ✓
#
# Bank debits
# - ACH Debit: ✗
# - Canadian PADs: ✗
# - BACS Direct Debit: ✗
# - SEPA Direct Debit: ✓
# - BECS Direct Debit: ✗
#
# Bank redirects
# - Bancontact: ✓
# - BLIK: ✗
# - EPS: ✓
# - giropay: ✓
# - iDEAL: ✓
# - P24: ✓
# - Sofort: ✓
# - FPX: ✗
# - PayNow: ✗
# - UPI: ✗
# - Netbanking: ✗
#
# Bank transfers
# - ACH Bank Transfer: ✗
# - SEPA Bank Transfer: ✗
# - UK Bank Transfer: ✗
# - Multibanco: ✗
# - Furikomi (Japan): ✗
# - Mexico Bank Transfer: ✗
#
# Buy now, pay later
# - Affirm: ✗
# - Afterpay/Clearpay: ✗
# - Klarna: ✗
#
# Real-time payments
# - PayNow: ✗
# - PromptPay: ✗
# - Pix: ✗
#
# Vouchers
# - Konbini: ✗
# - OXXO: ✗
# - Boleto: ✗
#
# Wallets
# - Apple Pay: ✓ (Cards)
# - Google Pay: ✓ (Cards)
# - Secure Remote Commerce: ✗
# - Link: ✓ (PaymentRequestButton)
# - Cash App Pay: ✗
# - MobilePay: ✗
# - Alipay: ✓
# - WeChat Pay: ✓
# - GrabPay: ✓


class StripeSettingsHolder(BasePaymentProvider):
    identifier = 'stripe_settings'
    verbose_name = _('Stripe')
    is_enabled = False
    is_meta = True

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('payment', 'stripe', event)

    def get_connect_url(self, request):
        request.session['payment_stripe_oauth_event'] = request.event.pk
        if 'payment_stripe_oauth_token' not in request.session:
            request.session['payment_stripe_oauth_token'] = get_random_string(32)
        return (
            "https://connect.stripe.com/oauth/authorize?response_type=code&client_id={}&state={}"
            "&scope=read_write&redirect_uri={}"
        ).format(
            self.settings.connect_client_id,
            request.session['payment_stripe_oauth_token'],
            urllib.parse.quote(build_global_uri('plugins:stripe:oauth.return')),
        )

    def settings_content_render(self, request):
        if self.settings.connect_client_id and not self.settings.secret_key:
            # Use Stripe connect
            if not self.settings.connect_user_id:
                return (
                    "<p>{}</p>"
                    "<a href='{}' class='btn btn-primary btn-lg'>{}</a>"
                ).format(
                    _('To accept payments via Stripe, you will need an account at Stripe. By clicking on the '
                      'following button, you can either create a new Stripe account connect pretix to an existing '
                      'one.'),
                    self.get_connect_url(request),
                    _('Connect with Stripe')
                )
            else:
                return (
                    "<a href='{}' class='btn btn-danger'>{}</a>"
                ).format(
                    reverse('plugins:stripe:oauth.disconnect', kwargs={
                        'organizer': self.event.organizer.slug,
                        'event': self.event.slug,
                    }),
                    _('Disconnect from Stripe')
                )
        else:
            return "<div class='alert alert-info'>%s<br /><code>%s</code></div>" % (
                _('Please configure a <a href="https://dashboard.stripe.com/account/webhooks">Stripe Webhook</a> to '
                  'the following endpoint in order to automatically cancel orders when charges are refunded externally '
                  'and to process asynchronous payment methods like SOFORT.'),
                build_global_uri('plugins:stripe:webhook')
            )

    @property
    def settings_form_fields(self):
        if 'pretix_resellers' in [p.module for p in get_all_plugins()]:
            moto_settings = [
                ('reseller_moto',
                 forms.BooleanField(
                     label=_('Enable MOTO payments for resellers'),
                     help_text=(
                         _('Gated feature (needs to be enabled for your account by Stripe support first)') +
                         '<div class="alert alert-danger">%s</div>' % _(
                             'We can flag the credit card transaction you make through the reseller interface as MOTO '
                             '(Mail Order / Telephone Order), which will exempt them from Strong Customer '
                             'Authentication (SCA) requirements. However: By enabling this feature, you will need to '
                             'fill out yearly PCI-DSS self-assessment forms like the 40 page SAQ D. Please consult the '
                             '%s for further information on this subject.' %
                             '<a href="https://stripe.com/docs/security">{}</a>'.format(
                                 _('Stripe Integration security guide')
                             )
                         )
                     ),
                     required=False,
                 ))
            ]
        else:
            moto_settings = []

        if self.settings.connect_client_id and not self.settings.secret_key:
            # Stripe connect
            if self.settings.connect_user_id:
                fields = [
                    ('connect_user_name',
                     forms.CharField(
                         label=_('Stripe account'),
                         disabled=True
                     )),
                    ('connect_user_id',
                     forms.CharField(
                         label=_('Stripe account'),
                         disabled=True
                     )),
                    ('endpoint',
                     forms.ChoiceField(
                         label=_('Endpoint'),
                         initial='live',
                         choices=(
                             ('live', pgettext('stripe', 'Live')),
                             ('test', pgettext('stripe', 'Testing')),
                         ),
                         help_text=_('If your event is in test mode, we will always use Stripe\'s test API, '
                                     'regardless of this setting.')
                     )),
                ]
            else:
                return {}
        else:
            allcountries = list(countries)
            allcountries.insert(0, ('', _('Select country')))

            fields = [
                ('publishable_key',
                 forms.CharField(
                     label=_('Publishable key'),
                     help_text=_('<a target="_blank" rel="noopener" href="{docs_url}">{text}</a>').format(
                         text=_('Click here for a tutorial on how to obtain the required keys'),
                         docs_url='https://docs.pretix.eu/en/latest/user/payments/stripe.html'
                     ),
                     validators=(
                         StripeKeyValidator('pk_'),
                     ),
                 )),
                ('secret_key',
                 SecretKeySettingsField(
                     label=_('Secret key'),
                     validators=(
                         StripeKeyValidator(['sk_', 'rk_']),
                     ),
                 )),
                ('merchant_country',
                 forms.ChoiceField(
                     choices=allcountries,
                     label=_('Merchant country'),
                     help_text=_('The country in which your Stripe-account is registered in. Usually, this is your '
                                 'country of residence.'),
                 )),
            ]

        extra_fields = [
            ('walletdetection',
             forms.BooleanField(
                 label=mark_safe(
                     _('Check for Apple Pay/Google Pay') +
                     ' ' +
                     '<span class="label label-info">{}</span>'.format(_('experimental'))
                 ),
                 help_text=_("pretix will attempt to check if the customer's web browser supports wallet-based payment "
                             "methods like Apple Pay or Google Pay and display them prominently with the credit card "
                             "payment method. This detection does not take into consideration if Google Pay/Apple Pay "
                             "has been disabled in the Stripe Dashboard."),
                 initial=True,
                 required=False,
             )),
            ('postfix',
             forms.CharField(
                 label=_('Statement descriptor postfix'),
                 help_text=_('Any value entered here will be shown on the customer\'s credit card bill or bank account '
                             'transaction. We will automatically add the order code in front of it. Note that depending '
                             'on the payment method, only a very limited number of characters is allowed. We do not '
                             'recommend entering more than {cnt} characters into this field.').format(
                     cnt=22 - 1 - settings.ENTROPY['order_code']
                 ),
                 required=False,
             )),
        ]

        d = OrderedDict(
            fields + [
                ('method_card',
                 forms.BooleanField(
                     label=_('Credit card payments'),
                     required=False,
                 )),
                ('method_giropay',
                 forms.BooleanField(
                     label=_('giropay'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Needs to be enabled in your Stripe account first.'),
                     required=False,
                 )),
                ('method_ideal',
                 forms.BooleanField(
                     label=_('iDEAL'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Needs to be enabled in your Stripe account first.'),
                     required=False,
                 )),
                ('method_alipay',
                 forms.BooleanField(
                     label=_('Alipay'),
                     disabled=self.event.currency not in ('EUR', 'AUD', 'CAD', 'GBP', 'HKD', 'JPY', 'NZD', 'SGD', 'USD'),
                     help_text=_('Needs to be enabled in your Stripe account first.'),
                     required=False,
                 )),
                ('method_bancontact',
                 forms.BooleanField(
                     label=_('Bancontact'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Needs to be enabled in your Stripe account first.'),
                     required=False,
                 )),
                ('method_sepa_debit',
                 forms.BooleanField(
                     label=_('SEPA Direct Debit'),
                     disabled=self.event.currency != 'EUR',
                     help_text=(
                         _('Needs to be enabled in your Stripe account first.') +
                         '<div class="alert alert-warning">%s</div>' % _(
                             'SEPA Direct Debit payments via Stripe are <strong>not</strong> processed '
                             'instantly but might take up to <strong>14 days</strong> to be confirmed in some cases. '
                             'Please only activate this payment method if your payment term allows for this lag.'
                         )),
                     required=False,
                 )),
                ('sepa_creditor_name',
                 forms.CharField(
                     label=_('SEPA Creditor Mandate Name'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Please provide your SEPA Creditor Mandate Name, that will be displayed to the user.'),
                     required=False,
                     widget=forms.TextInput(
                         attrs={
                             'data-display-dependency': '#id_payment_stripe_method_sepa_debit',
                             'data-required-if': '#id_payment_stripe_method_sepa_debit'
                         }
                     ),
                 )),
                ('method_sofort',
                 forms.BooleanField(
                     label=_('SOFORT'),
                     disabled=self.event.currency != 'EUR',
                     help_text=(
                         _('Needs to be enabled in your Stripe account first.') +
                         '<div class="alert alert-warning">%s</div>' % _(
                             'Despite the name, Sofort payments via Stripe are <strong>not</strong> processed '
                             'instantly but might take up to <strong>14 days</strong> to be confirmed in some cases. '
                             'Please only activate this payment method if your payment term allows for this lag.'
                         )
                     ),
                     required=False,
                 )),
                ('method_eps',
                 forms.BooleanField(
                     label=_('EPS'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Needs to be enabled in your Stripe account first.'),
                     required=False,
                 )),
                ('method_multibanco',
                 forms.BooleanField(
                     label=_('Multibanco'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Needs to be enabled in your Stripe account first.'),
                     required=False,
                 )),
                ('method_przelewy24',
                 forms.BooleanField(
                     label=_('Przelewy24'),
                     disabled=self.event.currency not in ['EUR', 'PLN'],
                     help_text=_('Needs to be enabled in your Stripe account first.'),
                     required=False,
                 )),
                ('method_wechatpay',
                 forms.BooleanField(
                     label=_('WeChat Pay'),
                     disabled=self.event.currency not in ['AUD', 'CAD', 'EUR', 'GBP', 'HKD', 'JPY', 'SGD', 'USD'],
                     help_text=_('Needs to be enabled in your Stripe account first.'),
                     required=False,
                 )),
            ] + extra_fields + list(super().settings_form_fields.items()) + moto_settings
        )
        if not self.settings.connect_client_id or self.settings.secret_key:
            d['connect_destination'] = forms.CharField(
                label=_('Destination'),
                validators=(
                    StripeKeyValidator(['acct_']),
                ),
                required=False
            )
        d.move_to_end('_enabled', last=False)
        return d


class StripeMethod(BasePaymentProvider):
    identifier = ''
    method = ''

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('payment', 'stripe', event)

    @property
    def test_mode_message(self):
        if self.settings.connect_client_id and not self.settings.secret_key:
            is_testmode = True
        else:
            is_testmode = self.settings.secret_key and '_test_' in self.settings.secret_key
        if is_testmode:
            return mark_safe(
                _('The Stripe plugin is operating in test mode. You can use one of <a {args}>many test '
                  'cards</a> to perform a transaction. No money will actually be transferred.').format(
                    args='href="https://stripe.com/docs/testing#cards" target="_blank"'
                )
            )
        return None

    @property
    def settings_form_fields(self):
        return {}

    @property
    def is_enabled(self) -> bool:
        return self.settings.get('_enabled', as_type=bool) and self.settings.get('method_{}'.format(self.method),
                                                                                 as_type=bool)

    def payment_refund_supported(self, payment: OrderPayment) -> bool:
        return True

    def payment_partial_refund_supported(self, payment: OrderPayment) -> bool:
        return True

    def payment_prepare(self, request, payment):
        return self.checkout_prepare(request, None)

    def _amount_to_decimal(self, cents):
        places = settings.CURRENCY_PLACES.get(self.event.currency, 2)
        return round_decimal(float(cents) / (10 ** places), self.event.currency)

    def _decimal_to_int(self, amount):
        places = settings.CURRENCY_PLACES.get(self.event.currency, 2)
        return int(amount * 10 ** places)

    def _get_amount(self, payment):
        return self._decimal_to_int(payment.amount)

    def _connect_kwargs(self, payment):
        d = {}
        if self.settings.connect_client_id and self.settings.connect_user_id and not self.settings.secret_key:
            fee = Decimal('0.00')
            if self.settings.get('connect_app_fee_percent', as_type=Decimal):
                fee = round_decimal(self.settings.get('connect_app_fee_percent', as_type=Decimal) * payment.amount / Decimal('100.00'), self.event.currency)
            if self.settings.connect_app_fee_max:
                fee = min(fee, self.settings.get('connect_app_fee_max', as_type=Decimal))
            if self.settings.get('connect_app_fee_min', as_type=Decimal):
                fee = max(fee, self.settings.get('connect_app_fee_min', as_type=Decimal))
            if fee:
                d['application_fee_amount'] = self._decimal_to_int(fee)
        if self.settings.connect_destination:
            d['transfer_data'] = {
                'destination': self.settings.connect_destination
            }
        return d

    def statement_descriptor(self, payment, length=22):
        if self.settings.postfix:
            # If a custom postfix is set, we only transmit the order code, so we have as much room as possible for
            # the postfix.
            return '{code} {postfix}'.format(
                code=payment.order.code,
                postfix=self.settings.postfix,
            )[:length]
        else:
            # If no custom postfix is set, we transmit the event slug and event name for backwards compatibility
            # with older pretix versions.
            return '{event}-{code} {eventname}'.format(
                event=self.event.slug.upper(),
                code=payment.order.code,
                eventname=re.sub('[^a-zA-Z0-9 ]', '', str(self.event.name))
            )[:length]

    @property
    def api_kwargs(self):
        if self.settings.connect_client_id and self.settings.connect_user_id and not self.settings.secret_key:
            if self.settings.get('endpoint', 'live') == 'live' and not self.event.testmode:
                kwargs = {
                    'api_key': self.settings.connect_secret_key,
                    'stripe_account': self.settings.connect_user_id
                }
            else:
                kwargs = {
                    'api_key': self.settings.connect_test_secret_key,
                    'stripe_account': self.settings.connect_user_id
                }
        else:
            kwargs = {
                'api_key': self.settings.secret_key,
            }
        return kwargs

    def _init_api(self):
        stripe.api_version = '2022-08-01'
        stripe.set_app_info(
            "pretix",
            partner_id="pp_partner_FSaz4PpKIur7Ox",
            version=__version__,
            url="https://pretix.eu"
        )

    def checkout_confirm_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_confirm.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings, 'provider': self}
        return template.render(ctx)

    def payment_can_retry(self, payment):
        return self._is_still_available(order=payment.order)

    def _charge_source(self, request, source, payment):
        try:
            params = {}
            if not source.startswith('src_'):
                params['statement_descriptor'] = self.statement_descriptor(payment)
            params.update(self.api_kwargs)
            params.update(self._connect_kwargs(payment))
            charge = stripe.Charge.create(
                amount=self._get_amount(payment),
                currency=self.event.currency.lower(),
                source=source,
                description='{event}-{code}'.format(
                    event=self.event.slug.upper(),
                    code=payment.order.code
                ),
                metadata={
                    'order': str(payment.order.id),
                    'event': self.event.id,
                    'code': payment.order.code
                },
                # TODO: Is this sufficient?
                idempotency_key=str(self.event.id) + payment.order.code + source,
                **params
            )
        except stripe.error.CardError as e:
            if e.json_body:
                err = e.json_body['error']
                logger.exception('Stripe error: %s' % str(err))
            else:
                err = {'message': str(e)}
                logger.exception('Stripe error: %s' % str(e))
            logger.info('Stripe card error: %s' % str(err))
            payment.fail(info={
                'error': True,
                'message': err['message'],
            })
            raise PaymentException(_('Stripe reported an error with your card: %s') % err['message'])

        except stripe.error.StripeError as e:
            if e.json_body and 'error' in e.json_body:
                err = e.json_body['error']
                logger.exception('Stripe error: %s' % str(err))

                if err.get('code') == 'idempotency_key_in_use':
                    # This is not an error we normally expect, however some payment methods like iDEAL will redirect
                    # the user back to our confirmation page at the same time from two devices: the web browser the
                    # purchase is executed from and the online banking app the payment is authorized from.
                    # In this case we will just log the idempotency error but not expose it to the user and just
                    # forward them back to their order page. There is a good chance that by the time the user hits
                    # the order page, the other request has gone through and the payment is confirmed.
                    # Usually however this should be prevented by SELECT FOR UPDATE calls!
                    return

            else:
                err = {'message': str(e)}
                logger.exception('Stripe error: %s' % str(e))

            payment.fail(info={
                'error': True,
                'message': err['message'],
            })
            raise PaymentException(_('We had trouble communicating with Stripe. Please try again and get in touch '
                                     'with us if this problem persists.'))
        else:
            ReferencedStripeObject.objects.get_or_create(
                reference=charge.id,
                defaults={'order': payment.order, 'payment': payment}
            )
            if charge.status == 'succeeded' and charge.paid:
                try:
                    payment.info = str(charge)
                    payment.confirm()
                except Quota.QuotaExceededException as e:
                    raise PaymentException(str(e))

                except SendMailException:
                    raise PaymentException(_('There was an error sending the confirmation mail.'))
            elif charge.status == 'pending':
                if request:
                    messages.warning(request, _('Your payment is pending completion. We will inform you as soon as the '
                                                'payment completed.'))
                payment.info = str(charge)
                payment.state = OrderPayment.PAYMENT_STATE_PENDING
                payment.save()
                return
            else:
                logger.info('Charge failed: %s' % str(charge))
                payment.fail(info=str(charge))
                raise PaymentException(_('Stripe reported an error: %s') % charge.failure_message)

    def payment_pending_render(self, request, payment) -> str:
        if payment.info:
            payment_info = json.loads(payment.info)
        else:
            payment_info = None
        template = get_template('pretixplugins/stripe/pending.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'provider': self,
            'order': payment.order,
            'payment': payment,
            'payment_info': payment_info,
            'payment_hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest()
        }
        return template.render(ctx)

    def matching_id(self, payment: OrderPayment):
        return payment.info_data.get("id", None)

    def refund_matching_id(self, refund: OrderRefund):
        return refund.info_data.get('id', None)

    def api_payment_details(self, payment: OrderPayment):
        return {
            "id": payment.info_data.get("id", None),
            "payment_method": payment.info_data.get("payment_method", None)
        }

    def api_refund_details(self, refund: OrderRefund):
        return {
            "id": refund.info_data.get("id", None),
        }

    def payment_control_render(self, request, payment) -> str:
        if payment.info:
            payment_info = json.loads(payment.info)
            if 'amount' in payment_info:
                payment_info['amount'] /= 10 ** settings.CURRENCY_PLACES.get(self.event.currency, 2)
        else:
            payment_info = None
        template = get_template('pretixplugins/stripe/control.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'payment_info': payment_info,
            'payment': payment,
            'method': self.method,
            'provider': self,
        }
        return template.render(ctx)

    @transaction.atomic()
    def execute_refund(self, refund: OrderRefund):
        self._init_api()

        payment_info = refund.payment.info_data
        OrderPayment.objects.select_for_update(of=OF_SELF).get(pk=refund.payment.pk)

        if not payment_info:
            raise PaymentException(_('No payment information found.'))

        try:
            if payment_info['id'].startswith('pi_'):
                chargeid = payment_info['charges']['data'][0]['id']
            else:
                chargeid = payment_info['id']

            ch = stripe.Charge.retrieve(chargeid, **self.api_kwargs)
            kwargs = {}
            if self.settings.connect_destination:
                kwargs['reverse_transfer'] = True
            r = ch.refunds.create(
                amount=self._get_amount(refund),
                **kwargs,
            )
            ch.refresh()
        except (stripe.error.InvalidRequestError, stripe.error.AuthenticationError, stripe.error.APIConnectionError) \
                as e:
            if e.json_body and 'error' in e.json_body:
                err = e.json_body['error']
                logger.exception('Stripe error: %s' % str(err))
            else:
                err = {'message': str(e)}
                logger.exception('Stripe error: %s' % str(e))

            refund.info_data = err
            refund.state = OrderRefund.REFUND_STATE_FAILED
            refund.execution_date = now()
            refund.save()
            refund.order.log_action('pretix.event.order.refund.failed', {
                'local_id': refund.local_id,
                'provider': refund.provider,
                'error': str(e)
            })
            raise PaymentException(_('We had trouble communicating with Stripe. Please try again and contact '
                                     'support if the problem persists.'))
        except stripe.error.StripeError as err:
            logger.error('Stripe error: %s' % str(err))
            raise PaymentException(_('Stripe returned an error'))
        else:
            refund.info = str(r)
            if r.status in ('succeeded', 'pending'):
                refund.done()
            elif r.status in ('failed', 'canceled'):
                refund.state = OrderRefund.REFUND_STATE_FAILED
                refund.execution_date = now()
                refund.save()

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        self._init_api()
        try:
            source = self._create_source(request, payment)

        except stripe.error.StripeError as e:
            if e.json_body and 'err' in e.json_body:
                err = e.json_body['error']
                logger.exception('Stripe error: %s' % str(err))

                if err.get('code') == 'idempotency_key_in_use':
                    # Same thing happening twice – we don't want to record a failure, as that might prevent the
                    # other thread from succeeding.
                    return
            else:
                err = {'message': str(e)}
                logger.exception('Stripe error: %s' % str(e))
            payment.fail(info={
                'error': True,
                'message': err['message'],
            })
            raise PaymentException(_('We had trouble communicating with Stripe. Please try again and get in touch '
                                     'with us if this problem persists.'))

        ReferencedStripeObject.objects.get_or_create(
            reference=source.id,
            defaults={'order': payment.order, 'payment': payment}
        )
        payment.info = str(source)
        payment.state = OrderPayment.PAYMENT_STATE_PENDING
        payment.save()
        request.session['payment_stripe_order_secret'] = payment.order.secret
        return self.redirect(request, source.redirect.url)

    def redirect(self, request, url):
        if request.session.get('iframe_session', False):
            return (
                build_absolute_uri(request.event, 'plugins:stripe:redirect') +
                '?data=' + signing.dumps({
                    'url': url,
                    'session': {
                        'payment_stripe_order_secret': request.session['payment_stripe_order_secret'],
                    },
                }, salt='safe-redirect')
            )
        else:
            return str(url)

    def shred_payment_info(self, obj: OrderPayment):
        if not obj.info:
            return
        d = json.loads(obj.info)
        new = {}
        if d.get('source'):
            new['source'] = {
                'id': d['source'].get('id'),
                'type': d['source'].get('type'),
                'brand': d['source'].get('brand'),
                'last4': d['source'].get('last4'),
                'bank_name': d['source'].get('bank_name'),
                'bank': d['source'].get('bank'),
                'bic': d['source'].get('bic'),
                'card': {
                    'brand': d['source'].get('card', {}).get('brand'),
                    'country': d['source'].get('card', {}).get('cuntry'),
                    'last4': d['source'].get('card', {}).get('last4'),
                }
            }
        if 'amount' in d:
            new['amount'] = d['amount']
        if 'currency' in d:
            new['currency'] = d['currency']
        if 'status' in d:
            new['status'] = d['status']
        if 'id' in d:
            new['id'] = d['id']

        new['_shredded'] = True
        obj.info = json.dumps(new)
        obj.save(update_fields=['info'])

        for le in obj.order.all_logentries().filter(
                action_type="pretix.plugins.stripe.event"
        ).exclude(data="", shredded=True):
            d = le.parsed_data
            if 'data' in d:
                for k, v in list(d['data']['object'].items()):
                    if v not in ('reason', 'status', 'failure_message', 'object', 'id'):
                        d['data']['object'][k] = '█'
                le.data = json.dumps(d)
                le.shredded = True
                le.save(update_fields=['data', 'shredded'])


class StripePaymentIntentMethod(StripeMethod):
    identifier = ''
    method = ''

    def payment_is_valid_session(self, request):
        return request.session.get('payment_stripe_{}_payment_method_id'.format(self.method), '') != ''

    def checkout_prepare(self, request, cart):
        payment_method_id = request.POST.get('stripe_{}_payment_method_id'.format(self.method), '')
        request.session['payment_stripe_{}_payment_method_id'.format(self.method)] = payment_method_id

        if payment_method_id == '':
            messages.warning(request, _('You may need to enable JavaScript for Stripe payments.'))
            return False
        return True

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        try:
            return self._handle_payment_intent(request, payment)
        finally:
            del request.session['payment_stripe_{}_payment_method_id'.format(self.method)]

    def is_moto(self, request, payment=None) -> bool:
        return False

    def _payment_intent_kwargs(self, request, payment):
        return {}

    def _handle_payment_intent(self, request, payment, intent=None):
        self._init_api()

        try:
            if self.payment_is_valid_session(request):
                params = {}
                params.update(self._connect_kwargs(payment))
                params.update(self.api_kwargs)
                params.update(self._payment_intent_kwargs(request, payment))

                if self.is_moto(request, payment):
                    params.update({
                        'payment_method_options': {
                            'card': {
                                'moto': True
                            }
                        }
                    })

                intent = stripe.PaymentIntent.create(
                    amount=self._get_amount(payment),
                    currency=self.event.currency.lower(),
                    payment_method=request.session['payment_stripe_{}_payment_method_id'.format(self.method)],
                    payment_method_types=[self.method],
                    confirmation_method='manual',
                    confirm=True,
                    description='{event}-{code}'.format(
                        event=self.event.slug.upper(),
                        code=payment.order.code
                    ),
                    statement_descriptor=self.statement_descriptor(payment),
                    metadata={
                        'order': str(payment.order.id),
                        'event': self.event.id,
                        'code': payment.order.code
                    },
                    # TODO: Is this sufficient?
                    idempotency_key=str(self.event.id) + payment.order.code + request.session['payment_stripe_{}_payment_method_id'.format(self.method)],
                    return_url=build_absolute_uri(self.event, 'plugins:stripe:sca.return', kwargs={
                        'order': payment.order.code,
                        'payment': payment.pk,
                        'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
                    }),
                    **params
                )
            else:
                payment_info = json.loads(payment.info)

                if 'id' in payment_info:
                    if not intent:
                        intent = stripe.PaymentIntent.retrieve(
                            payment_info['id'],
                            **self.api_kwargs
                        )
                else:
                    return

        except stripe.error.CardError as e:
            if e.json_body:
                err = e.json_body['error']
                logger.exception('Stripe error: %s' % str(err))
            else:
                err = {'message': str(e)}
                logger.exception('Stripe error: %s' % str(e))
            logger.info('Stripe card error: %s' % str(err))
            payment.fail(info={
                'error': True,
                'message': err['message'],
            })
            raise PaymentException(_('Stripe reported an error with your card: %s') % err['message'])

        except stripe.error.StripeError as e:
            if e.json_body and 'error' in e.json_body:
                err = e.json_body['error']
                logger.exception('Stripe error: %s' % str(err))

                if err.get('code') == 'idempotency_key_in_use':
                    # Same thing happening twice – we don't want to record a failure, as that might prevent the
                    # other thread from succeeding.
                    return
            else:
                err = {'message': str(e)}
                logger.exception('Stripe error: %s' % str(e))
            payment.fail(info={
                'error': True,
                'message': err['message'],
            })
            raise PaymentException(_('We had trouble communicating with Stripe. Please try again and get in touch '
                                     'with us if this problem persists.'))
        else:
            ReferencedStripeObject.objects.get_or_create(
                reference=intent.id,
                defaults={'order': payment.order, 'payment': payment}
            )
            if intent.status == 'requires_action':
                payment.info = str(intent)
                payment.state = OrderPayment.PAYMENT_STATE_CREATED
                payment.save()
                return build_absolute_uri(self.event, 'plugins:stripe:sca', kwargs={
                    'order': payment.order.code,
                    'payment': payment.pk,
                    'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
                })

            if intent.status == 'requires_confirmation':
                payment.info = str(intent)
                payment.state = OrderPayment.PAYMENT_STATE_CREATED
                payment.save()
                self._confirm_payment_intent(request, payment)

            elif intent.status == 'succeeded' and intent.charges.data[-1].paid:
                try:
                    payment.info = str(intent)
                    payment.confirm()
                except Quota.QuotaExceededException as e:
                    raise PaymentException(str(e))

                except SendMailException:
                    raise PaymentException(_('There was an error sending the confirmation mail.'))
            elif intent.status == 'processing':
                if request:
                    messages.warning(request, _('Your payment is pending completion. We will inform you as soon as the '
                                                'payment completed.'))
                payment.info = str(intent)
                payment.state = OrderPayment.PAYMENT_STATE_PENDING
                payment.save()
                return
            elif intent.status == 'requires_payment_method':
                if request:
                    messages.warning(request, _('Your payment failed. Please try again.'))
                payment.fail(info=str(intent))
                return
            else:
                logger.info('Charge failed: %s' % str(intent))
                payment.fail(info=str(intent))
                raise PaymentException(_('Stripe reported an error: %s') % intent.last_payment_error.message)

    def _confirm_payment_intent(self, request, payment):
        self._init_api()

        try:
            payment_info = json.loads(payment.info)

            intent = stripe.PaymentIntent.confirm(
                payment_info['id'],
                return_url=build_absolute_uri(self.event, 'plugins:stripe:sca.return', kwargs={
                    'order': payment.order.code,
                    'payment': payment.pk,
                    'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
                }),
                **self.api_kwargs
            )

            payment.info = str(intent)
            payment.save()

            self._handle_payment_intent(request, payment)
        except stripe.error.CardError as e:
            if e.json_body:
                err = e.json_body['error']
                logger.exception('Stripe error: %s' % str(err))
            else:
                err = {'message': str(e)}
                logger.exception('Stripe error: %s' % str(e))
            logger.info('Stripe card error: %s' % str(err))
            payment.fail(info={
                'error': True,
                'message': err['message'],
            })
            raise PaymentException(_('Stripe reported an error with your card: %s') % err['message'])
        except stripe.error.InvalidRequestError as e:
            if e.json_body:
                err = e.json_body['error']
                logger.exception('Stripe error: %s' % str(err))
            else:
                err = {'message': str(e)}
                logger.exception('Stripe error: %s' % str(e))
            payment.fail(info={
                'error': True,
                'message': err['message'],
            })
            raise PaymentException(_('We had trouble communicating with Stripe. Please try again and get in touch '
                                     'with us if this problem persists.'))


class StripeCC(StripePaymentIntentMethod):
    identifier = 'stripe'
    verbose_name = _('Credit card via Stripe')
    public_name = _('Credit card')
    method = 'card'

    @property
    def walletqueries(self):
        # ToDo: Check against Stripe API, if ApplePay and GooglePay are even activated/available
        # This is probably only really feasable once the Payment Methods Configuration API is out of beta
        # https://stripe.com/docs/connect/payment-method-configurations
        if self.settings.get("walletdetection", True, as_type=bool):
            return [WalletQueries.APPLEPAY, WalletQueries.GOOGLEPAY]
        return []

    def payment_form_render(self, request, total, order=None) -> str:
        account = get_stripe_account_key(self)
        if not RegisteredApplePayDomain.objects.filter(account=account, domain=request.host).exists():
            stripe_verify_domain.apply_async(args=(self.event.pk, request.host))

        template = get_template('pretixplugins/stripe/checkout_payment_form_card.html')
        ctx = {
            'request': request,
            'event': self.event,
            'total': self._decimal_to_int(total),
            'settings': self.settings,
            'is_moto': self.is_moto(request)
        }
        return template.render(ctx)

    def _migrate_session(self, request):
        # todo: remove after pretix 2023.8 was released
        keymap = {
            'payment_stripe_payment_method_id': 'payment_stripe_card_payment_method_id',
            'payment_stripe_brand': 'payment_stripe_card_brand',
            'payment_stripe_last4': 'payment_stripe_card_last4',
        }
        for old, new in keymap.items():
            if old in request.session:
                request.session[new] = request.session[old]
                del request.session[old]

    def checkout_prepare(self, request, cart):
        self._migrate_session(request)
        request.session['payment_stripe_card_brand'] = request.POST.get('stripe_card_brand', '')
        request.session['payment_stripe_card_last4'] = request.POST.get('stripe_card_last4', '')

        return super().checkout_prepare(request, cart)

    def payment_is_valid_session(self, request):
        self._migrate_session(request)
        return super().payment_is_valid_session(request)

    def _handle_payment_intent(self, request, payment, intent=None):
        self._migrate_session(request)
        return super()._handle_payment_intent(request, payment, intent)

    def is_moto(self, request, payment=None) -> bool:
        # We don't have a payment yet when checking if we should display the MOTO-flag
        # However, before we execute the payment, we absolutely have to check if the request-SalesChannel as well as the
        # order are tagged as a reseller-transaction. Else, a user with a valid reseller-session might be able to place
        # a MOTO transaction trough the WebShop.

        moto = self.settings.get('reseller_moto', False, as_type=bool) and \
            request.sales_channel.identifier == 'resellers'

        if payment:
            return moto and payment.order.sales_channel == 'resellers'

        return moto

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            if "charges" in pi:
                card = pi["charges"]["data"][0]["payment_method_details"]["card"]
            else:
                card = pi["source"]["card"]
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)
        return f'{self.public_name}: ' \
               f'{card.get("brand", "").title()} ' \
               f'************{card.get("last4", "****")}, ' \
               f'{_("expires {month}/{year}").format(month=card.get("exp_month"), year=card.get("exp_year"))}'


class StripeSEPADirectDebit(StripePaymentIntentMethod):
    identifier = 'stripe_sepa_debit'
    verbose_name = _('SEPA Debit via Stripe')
    public_name = _('SEPA Debit')
    method = 'sepa_debit'
    ia = InvoiceAddress()

    def payment_form_render(self, request: HttpRequest, total: Decimal, order: Order=None) -> str:
        def get_invoice_address():
            if order and getattr(order, 'invoice_address', None):
                request._checkout_flow_invoice_address = order.invoice_address
            if not hasattr(request, '_checkout_flow_invoice_address'):
                cs = cart_session(request)
                iapk = cs.get('invoice_address')
                if not iapk:
                    request._checkout_flow_invoice_address = InvoiceAddress()
                else:
                    try:
                        request._checkout_flow_invoice_address = InvoiceAddress.objects.get(pk=iapk, order__isnull=True)
                    except InvoiceAddress.DoesNotExist:
                        request._checkout_flow_invoice_address = InvoiceAddress()
            return request._checkout_flow_invoice_address

        cs = cart_session(request)
        self.ia = get_invoice_address()

        template = get_template('pretixplugins/stripe/checkout_payment_form_sepadirectdebit.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'form': self.payment_form(request),
            'email': order.email if order else cs.get('email', '')
        }
        return template.render(ctx)

    @property
    def payment_form_fields(self):
        return OrderedDict(
            [
                ('accountname',
                 forms.CharField(
                     label=_('Account Holder Name'),
                     initial=self.ia.name,
                 )),
                ('line1',
                 forms.CharField(
                     label=_('Account Holder Street'),
                     required=False,
                     widget=forms.TextInput(
                         attrs={
                             'data-display-dependency': '#stripe_sepa_debit_country',
                             'data-required-if': '#stripe_sepa_debit_country'
                         }
                     ),
                     initial=self.ia.street,
                 )),
                ('postal_code',
                 forms.CharField(
                     label=_('Account Holder Postal Code'),
                     required=False,
                     widget=forms.TextInput(
                         attrs={
                             'data-display-dependency': '#stripe_sepa_debit_country',
                             'data-required-if': '#stripe_sepa_debit_country'
                         }
                     ),
                     initial=self.ia.zipcode,
                 )),
                ('city',
                 forms.CharField(
                     label=_('Account Holder City'),
                     required=False,
                     widget=forms.TextInput(
                         attrs={
                             'data-display-dependency': '#stripe_sepa_debit_country',
                             'data-required-if': '#stripe_sepa_debit_country'
                         }
                     ),
                     initial=self.ia.city,
                 )),
                ('country',
                 forms.ChoiceField(
                     label=_('Account Holder Country'),
                     required=False,
                     choices=CachedCountries(),
                     widget=forms.Select(
                         attrs={
                             'data-display-dependency': '#stripe_sepa_debit_country',
                             'data-required-if': '#stripe_sepa_debit_country'
                         }
                     ),
                     initial=self.ia.country or guess_country(self.event),
                 )),
            ])

    def _payment_intent_kwargs(self, request, payment):
        return {
            'mandate_data': {
                'customer_acceptance': {
                    'type': 'online',
                    'online': {
                        'ip_address': get_client_ip(request),
                        'user_agent': request.META['HTTP_USER_AGENT'],
                    }
                },
            }
        }

    def checkout_prepare(self, request, cart):
        request.session['payment_stripe_sepa_debit_last4'] = request.POST.get('stripe_sepa_debit_last4', '')
        request.session['payment_stripe_sepa_debit_bank'] = request.POST.get('stripe_sepa_debit_bank', '')

        return super().checkout_prepare(request, cart)

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        try:
            super().execute_payment(request, payment)
        finally:
            fields = ['accountname', 'line1', 'postal_code', 'city', 'country']
            for field in fields:
                if 'payment_stripe_sepa_debit_{}'.format(field) in request.session:
                    del request.session['payment_stripe_sepa_debit_{}'.format(field)]


class StripeGiropay(StripeMethod):
    identifier = 'stripe_giropay'
    verbose_name = _('giropay via Stripe')
    public_name = _('giropay')
    method = 'giropay'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'form': self.payment_form(request)
        }
        return template.render(ctx)

    @property
    def payment_form_fields(self):
        return OrderedDict([
            ('account', forms.CharField(label=_('Account holder'))),
        ])

    def _create_source(self, request, payment):
        try:
            source = stripe.Source.create(
                type='giropay',
                amount=self._get_amount(payment),
                currency=self.event.currency.lower(),
                metadata={
                    'order': str(payment.order.id),
                    'event': self.event.id,
                    'code': payment.order.code
                },
                owner={
                    'name': request.session.get('payment_stripe_giropay_account') or gettext('unknown name')
                },
                statement_descriptor=self.statement_descriptor(payment, 35),
                redirect={
                    'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                        'order': payment.order.code,
                        'payment': payment.pk,
                        'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
                    })
                },
                **self.api_kwargs
            )
            return source
        finally:
            if 'payment_stripe_giropay_account' in request.session:
                del request.session['payment_stripe_giropay_account']

    def payment_is_valid_session(self, request):
        return (
            request.session.get('payment_stripe_giropay_account', '') != ''
        )

    def checkout_prepare(self, request, cart):
        form = self.payment_form(request)
        if form.is_valid():
            request.session['payment_stripe_giropay_account'] = form.cleaned_data['account']
            return True
        return False

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            return gettext('Bank account at {bank}').format(bank=pi["source"]["giropay"]["bank_name"])
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)


class StripeIdeal(StripeMethod):
    identifier = 'stripe_ideal'
    verbose_name = _('iDEAL via Stripe')
    public_name = _('iDEAL')
    method = 'ideal'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple_noform.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
        }
        return template.render(ctx)

    def _create_source(self, request, payment):
        source = stripe.Source.create(
            type='ideal',
            amount=self._get_amount(payment),
            currency=self.event.currency.lower(),
            metadata={
                'order': str(payment.order.id),
                'event': self.event.id,
                'code': payment.order.code
            },
            statement_descriptor=self.statement_descriptor(payment),
            redirect={
                'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                    'order': payment.order.code,
                    'payment': payment.pk,
                    'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
                })
            },
            **self.api_kwargs
        )
        return source

    def payment_is_valid_session(self, request):
        return True

    def checkout_prepare(self, request, cart):
        return True

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            return gettext('Bank account at {bank}').format(bank=pi["source"]["ideal"]["bank"])
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)


class StripeAlipay(StripeMethod):
    identifier = 'stripe_alipay'
    verbose_name = _('Alipay via Stripe')
    public_name = _('Alipay')
    method = 'alipay'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple_noform.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
        }
        return template.render(ctx)

    def _create_source(self, request, payment):
        source = stripe.Source.create(
            type='alipay',
            amount=self._get_amount(payment),
            currency=self.event.currency.lower(),
            metadata={
                'order': str(payment.order.id),
                'event': self.event.id,
                'code': payment.order.code
            },
            redirect={
                'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                    'order': payment.order.code,
                    'payment': payment.pk,
                    'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
                })
            },
            **self.api_kwargs
        )
        return source

    def payment_is_valid_session(self, request):
        return True

    def checkout_prepare(self, request, cart):
        return True


class StripeBancontact(StripeMethod):
    identifier = 'stripe_bancontact'
    verbose_name = _('Bancontact via Stripe')
    public_name = _('Bancontact')
    method = 'bancontact'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'form': self.payment_form(request)
        }
        return template.render(ctx)

    @property
    def payment_form_fields(self):
        return OrderedDict([
            ('account', forms.CharField(label=_('Account holder'), min_length=3)),
        ])

    def _create_source(self, request, payment):
        try:
            source = stripe.Source.create(
                type='bancontact',
                amount=self._get_amount(payment),
                currency=self.event.currency.lower(),
                metadata={
                    'order': str(payment.order.id),
                    'event': self.event.id,
                    'code': payment.order.code
                },
                owner={
                    'name': request.session.get('payment_stripe_bancontact_account') or gettext('unknown name')
                },
                statement_descriptor=self.statement_descriptor(payment, 35),
                redirect={
                    'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                        'order': payment.order.code,
                        'payment': payment.pk,
                        'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
                    })
                },
                **self.api_kwargs
            )
            return source
        finally:
            if 'payment_stripe_bancontact_account' in request.session:
                del request.session['payment_stripe_bancontact_account']

    def payment_is_valid_session(self, request):
        return (
            request.session.get('payment_stripe_bancontact_account', '') != ''
        )

    def checkout_prepare(self, request, cart):
        form = self.payment_form(request)
        if form.is_valid():
            request.session['payment_stripe_bancontact_account'] = form.cleaned_data['account']
            return True
        return False

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            return gettext('Bank account at {bank}').format(bank=pi["source"]["bancontact"]["bank_name"])
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)


class StripeSofort(StripeMethod):
    identifier = 'stripe_sofort'
    verbose_name = _('SOFORT via Stripe')
    public_name = _('SOFORT (instant bank transfer)')
    method = 'sofort'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'form': self.payment_form(request)
        }
        return template.render(ctx)

    @property
    def payment_form_fields(self):
        return OrderedDict([
            ('bank_country', forms.ChoiceField(label=_('Country of your bank'), choices=(
                ('de', _('Germany')),
                ('at', _('Austria')),
                ('be', _('Belgium')),
                ('nl', _('Netherlands')),
                ('es', _('Spain'))
            ))),
        ])

    def _create_source(self, request, payment):
        source = stripe.Source.create(
            type='sofort',
            amount=self._get_amount(payment),
            currency=self.event.currency.lower(),
            metadata={
                'order': str(payment.order.id),
                'event': self.event.id,
                'code': payment.order.code
            },
            statement_descriptor=self.statement_descriptor(payment, 35),
            sofort={
                'country': request.session.get('payment_stripe_sofort_bank_country'),
            },
            redirect={
                'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                    'order': payment.order.code,
                    'payment': payment.pk,
                    'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
                })
            },
            **self.api_kwargs
        )
        return source

    def payment_is_valid_session(self, request):
        return (
            request.session.get('payment_stripe_sofort_bank_country', '') != ''
        )

    def checkout_prepare(self, request, cart):
        form = self.payment_form(request)
        if form.is_valid():
            request.session['payment_stripe_sofort_bank_country'] = form.cleaned_data['bank_country']
            return True
        return False

    def payment_can_retry(self, payment):
        return payment.state != OrderPayment.PAYMENT_STATE_PENDING and self._is_still_available(order=payment.order)

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            return gettext('Bank account {iban} at {bank}').format(
                iban=f'{pi["source"]["sofort"]["country"]}****{pi["source"]["sofort"]["iban_last4"]}',
                bank=pi["source"]["sofort"]["bank_name"]
            )
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)


class StripeEPS(StripeMethod):
    identifier = 'stripe_eps'
    verbose_name = _('EPS via Stripe')
    public_name = _('EPS')
    method = 'eps'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'form': self.payment_form(request)
        }
        return template.render(ctx)

    @property
    def payment_form_fields(self):
        return OrderedDict([
            ('account', forms.CharField(label=_('Account holder'))),
        ])

    def _create_source(self, request, payment):
        try:
            source = stripe.Source.create(
                type='eps',
                amount=self._get_amount(payment),
                currency=self.event.currency.lower(),
                metadata={
                    'order': str(payment.order.id),
                    'event': self.event.id,
                    'code': payment.order.code
                },
                owner={
                    'name': request.session.get('payment_stripe_eps_account') or gettext('unknown name')
                },
                statement_descriptor=self.statement_descriptor(payment),
                redirect={
                    'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                        'order': payment.order.code,
                        'payment': payment.pk,
                        'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
                    })
                },
                **self.api_kwargs
            )
            return source
        finally:
            if 'payment_stripe_eps_account' in request.session:
                del request.session['payment_stripe_eps_account']

    def payment_is_valid_session(self, request):
        return (
            request.session.get('payment_stripe_eps_account', '') != ''
        )

    def checkout_prepare(self, request, cart):
        form = self.payment_form(request)
        if form.is_valid():
            request.session['payment_stripe_eps_account'] = form.cleaned_data['account']
            return True
        return False

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            return gettext('Bank account at {bank}').format(bank=pi["source"]["eps"]["bank"].replace('_', '').title())
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)


class StripeMultibanco(StripeMethod):
    identifier = 'stripe_multibanco'
    verbose_name = _('Multibanco via Stripe')
    public_name = _('Multibanco')
    method = 'multibanco'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple_noform.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'form': self.payment_form(request)
        }
        return template.render(ctx)

    def _create_source(self, request, payment):
        source = stripe.Source.create(
            type='multibanco',
            amount=self._get_amount(payment),
            currency=self.event.currency.lower(),
            metadata={
                'order': str(payment.order.id),
                'event': self.event.id,
                'code': payment.order.code
            },
            owner={
                'email': payment.order.email
            },
            redirect={
                'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                    'order': payment.order.code,
                    'payment': payment.pk,
                    'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
                })
            },
            **self.api_kwargs
        )
        return source

    def payment_is_valid_session(self, request):
        return True

    def checkout_prepare(self, request, cart):
        return True


class StripePrzelewy24(StripeMethod):
    identifier = 'stripe_przelewy24'
    verbose_name = _('Przelewy24 via Stripe')
    public_name = _('Przelewy24')
    method = 'przelewy24'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple_noform.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'form': self.payment_form(request)
        }
        return template.render(ctx)

    def _create_source(self, request, payment):
        source = stripe.Source.create(
            type='p24',
            amount=self._get_amount(payment),
            currency=self.event.currency.lower(),
            metadata={
                'order': str(payment.order.id),
                'event': self.event.id,
                'code': payment.order.code
            },
            owner={
                'email': payment.order.email
            },
            statement_descriptor=self.statement_descriptor(payment, 35),
            redirect={
                'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                    'order': payment.order.code,
                    'payment': payment.pk,
                    'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
                })
            },
            **self.api_kwargs
        )
        return source

    def payment_is_valid_session(self, request):
        return True

    def checkout_prepare(self, request, cart):
        return True

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            return gettext('Bank account at {bank}').format(bank=pi["source"]["p24"]["bank"].replace('_', '').title())
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)


class StripeWeChatPay(StripeMethod):
    identifier = 'stripe_wechatpay'
    verbose_name = _('WeChat Pay via Stripe')
    public_name = _('WeChat Pay')
    method = 'wechatpay'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple_noform.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'form': self.payment_form(request)
        }
        return template.render(ctx)

    def _create_source(self, request, payment):
        source = stripe.Source.create(
            type='wechat',
            amount=self._get_amount(payment),
            currency=self.event.currency.lower(),
            metadata={
                'order': str(payment.order.id),
                'event': self.event.id,
                'code': payment.order.code
            },
            statement_descriptor=self.statement_descriptor(payment, 32),
            redirect={
                'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                    'order': payment.order.code,
                    'payment': payment.pk,
                    'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
                })
            },
            **self.api_kwargs
        )
        return source

    def payment_is_valid_session(self, request):
        return True

    def checkout_prepare(self, request, cart):
        return True

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        self._init_api()
        try:
            source = self._create_source(request, payment)

        except stripe.error.StripeError as e:
            if e.json_body and 'err' in e.json_body:
                err = e.json_body['error']
                logger.exception('Stripe error: %s' % str(err))

                if err.get('code') == 'idempotency_key_in_use':
                    # Same thing happening twice – we don't want to record a failure, as that might prevent the
                    # other thread from succeeding.
                    return
            else:
                err = {'message': str(e)}
                logger.exception('Stripe error: %s' % str(e))
            payment.fail(info={
                'error': True,
                'message': err['message'],
            })
            raise PaymentException(_('We had trouble communicating with Stripe. Please try again and get in touch '
                                     'with us if this problem persists.'))

        ReferencedStripeObject.objects.get_or_create(
            reference=source.id,
            defaults={'order': payment.order, 'payment': payment}
        )
        payment.info = str(source)
        payment.save()

        return eventreverse(request.event, 'presale:event.order', kwargs={
            'order': payment.order.code,
            'secret': payment.order.secret
        })
