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

import json
import logging
import re
import urllib.parse
import zoneinfo
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from json import JSONDecodeError

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
from text_unidecode import unidecode

from pretix import __version__
from pretix.base.decimal import round_decimal
from pretix.base.forms import SecretKeySettingsField
from pretix.base.forms.questions import (
    guess_country, guess_country_from_request,
)
from pretix.base.models import (
    Event, InvoiceAddress, Order, OrderPayment, OrderRefund, Quota,
)
from pretix.base.payment import (
    BasePaymentProvider, PaymentException, WalletQueries,
)
from pretix.base.plugins import get_all_plugins
from pretix.base.settings import SettingsSandbox
from pretix.helpers import OF_SELF
from pretix.helpers.countries import CachedCountries
from pretix.helpers.http import get_client_ip
from pretix.helpers.urls import build_absolute_uri as build_global_uri
from pretix.multidomain.urlreverse import build_absolute_uri
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
# Last Update: 2023-12-20
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
# - giropay: (deprecated)
# - iDEAL: ✓
# - P24: ✓
# - Sofort: (deprecated)
# - FPX: ✗
# - PayNow: ✗
# - UPI: ✗
# - Netbanking: ✗
# - TWINT: ✓
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
# - Affirm: ✓
# - Afterpay/Clearpay: ✗
# - Klarna: ✓
# - Zip: ✗
#
# Real-time payments
# - Swish: ✓
# - PayNow: ✗
# - PromptPay: ✓
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
# - PayPal: ✓ (No settings UI yet)
# - MobilePay: ✓
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
                     help_text='<a target="_blank" rel="noopener" href="{docs_url}" class="btn btn-primary">{text}</a><br>'
                               '<p class="help-block">{help}</p>'.format(
                         text=_('Generate API keys'),
                         docs_url='https://marketplace.stripe.com/apps/install/link/eu.pretix.plugins.stripe.rak',
                         help=_('The button above will install our Stripe app to your account and will generate you '
                                'API keys with the recommended permission level for optimal usage with pretix.')
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
                ('method_ideal',
                 forms.BooleanField(
                     label=_('iDEAL'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                                 'before they work properly.'),
                     required=False,
                 )),
                ('method_alipay',
                 forms.BooleanField(
                     label=_('Alipay'),
                     disabled=self.event.currency not in ('EUR', 'AUD', 'CAD', 'GBP', 'HKD', 'JPY', 'NZD', 'SGD', 'USD'),
                     help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                                 'before they work properly.'),
                     required=False,
                 )),
                ('method_bancontact',
                 forms.BooleanField(
                     label=_('Bancontact'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                                 'before they work properly.'),
                     required=False,
                 )),
                ('method_sepa_debit',
                 forms.BooleanField(
                     label=_('SEPA Direct Debit'),
                     disabled=self.event.currency != 'EUR',
                     help_text=(
                         _('Some payment methods might need to be enabled in the settings of your Stripe account '
                           'before work properly.') +
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
                ('method_eps',
                 forms.BooleanField(
                     label=_('EPS'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                                 'before they work properly.'),
                     required=False,
                 )),
                ('method_multibanco',
                 forms.BooleanField(
                     label=_('Multibanco'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                                 'before they work properly.'),
                     required=False,
                 )),
                ('method_przelewy24',
                 forms.BooleanField(
                     label=_('Przelewy24'),
                     disabled=self.event.currency not in ['EUR', 'PLN'],
                     help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                                 'before they work properly.'),
                     required=False,
                 )),
                ('method_pay_by_bank',
                 forms.BooleanField(
                     label=_('Pay by bank'),
                     disabled=self.event.currency not in ['EUR', 'GBP'],
                     help_text=' '.join([
                         str(_('Some payment methods might need to be enabled in the settings of your Stripe account '
                               'before they work properly.')),
                         str(_('Currently only available for charges in GBP and customers with UK bank accounts, and '
                               'in private preview for France and Germany.'))
                     ]),
                     required=False,
                 )),
                ('method_wechatpay',
                 forms.BooleanField(
                     label=_('WeChat Pay'),
                     disabled=self.event.currency not in ['AUD', 'CAD', 'EUR', 'GBP', 'HKD', 'JPY', 'SGD', 'USD'],
                     help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                                 'before they work properly.'),
                     required=False,
                 )),
                ('method_revolut_pay',
                 forms.BooleanField(
                     label='Revolut Pay',
                     disabled=self.event.currency not in ['EUR', 'GBP', 'RON', 'HUF', 'PLN', 'DKK'],
                     help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                                 'before they work properly.'),
                     required=False,
                 )),
                ('method_promptpay',
                 forms.BooleanField(
                     label='PromptPay',
                     disabled=self.event.currency != 'THB',
                     help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                                 'before they work properly.'),
                     required=False,
                 )),
                ('method_swish',
                 forms.BooleanField(
                     label=_('Swish'),
                     disabled=self.event.currency != 'SEK',
                     help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                                 'before they work properly.'),
                     required=False,
                 )),
                ('method_twint',
                 forms.BooleanField(
                     label='TWINT',
                     disabled=self.event.currency != 'CHF',
                     help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                                 'before they work properly.'),
                     required=False,
                 )),
                ('method_affirm',
                 forms.BooleanField(
                     label=_('Affirm'),
                     disabled=self.event.currency not in ['USD', 'CAD'],
                     help_text=' '.join([
                         str(_('Some payment methods might need to be enabled in the settings of your Stripe account '
                               'before they work properly.')),
                         str(_('Only available for payments between $50 and $30,000.'))
                     ]),
                     required=False,
                 )),
                ('method_klarna',
                 forms.BooleanField(
                     label=_('Klarna'),
                     disabled=self.event.currency not in [
                         'AUD', 'CAD', 'CHF', 'CZK', 'DKK', 'EUR', 'GBP', 'NOK', 'NZD', 'PLN', 'SEK', 'USD'
                     ],
                     help_text=' '.join([
                         str(_('Some payment methods might need to be enabled in the settings of your Stripe account '
                               'before they work properly.')),
                         str(_('Klarna and Stripe will decide which of the payment methods offered by Klarna are '
                               'available to the user.')),
                         str(_('Klarna\'s terms of services do not allow it to be used by charities or political '
                               'organizations.')),
                     ]),
                     required=False,
                 )),
                # Disabled for now, since we still need to figure out how to make this work on our connect platform
                # ('method_paypal',
                #  forms.BooleanField(
                #      label=_('PayPal'),
                #      disabled=self.event.currency not in [
                #          'EUR', 'GBP', 'USD', 'CHF', 'CZK', 'DKK', 'NOK', 'PLN', 'SEK', 'AUD', 'CAD', 'HKD', 'NZD', 'SGD'
                #      ],
                #      help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                #                  'before they work properly.'),
                #      required=False,
                #  )),
                ('method_mobilepay',
                 forms.BooleanField(
                     label=_('MobilePay'),
                     disabled=self.event.currency not in ['DKK', 'EUR', 'NOK', 'SEK'],
                     help_text=_('Some payment methods might need to be enabled in the settings of your Stripe account '
                                 'before they work properly.'),
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
    redirect_action_handling = 'iframe'  # or redirect
    redirect_in_widget_allowed = True
    confirmation_method = 'manual'
    explanation = ''

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
                postfix=re.sub("[^a-zA-Z0-9-_. ]", "", unidecode(str(self.settings.postfix))),
            )[:length]
        else:
            # If no custom postfix is set, we transmit the event slug and event name for backwards compatibility
            # with older pretix versions.
            return '{event}-{code} {eventname}'.format(
                event=self.event.slug.upper(),
                code=payment.order.code,
                eventname=re.sub("[^a-zA-Z0-9-_. ]", "", unidecode(str(self.event.name))),
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
        stripe.api_version = '2023-10-16'
        stripe.set_app_info(
            "pretix",
            partner_id="pp_partner_FSaz4PpKIur7Ox",
            version=__version__,
            url="https://pretix.eu"
        )

    def checkout_confirm_render(self, request, **kwargs) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_confirm.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings, 'provider': self}
        return template.render(ctx)

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
            'payment_hash': payment.order.tagged_secret('plugins:stripe')
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
        try:
            return {
                "id": refund.info_data.get("id", None),
            }
        except JSONDecodeError:
            return {}

    def payment_control_render(self, request, payment) -> str:
        details = {}
        if payment.info:
            payment_info = json.loads(payment.info)
            if 'amount' in payment_info:
                payment_info['amount'] /= 10 ** settings.CURRENCY_PLACES.get(self.event.currency, 2)
            if isinstance(payment_info.get("latest_charge"), dict):
                details = payment_info["latest_charge"].get("payment_method_details", {})
            elif payment_info.get("charges") and payment_info["charges"]["data"]:
                details = payment_info["charges"]["data"][0].get("payment_method_details", {})
            elif payment_info.get("source"):
                details = payment_info["source"]
        else:
            payment_info = None
        details.setdefault('owner', {})

        template = get_template('pretixplugins/stripe/control.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'payment_info': payment_info,
            'payment': payment,
            'method': self.method,
            'details': details,
            'provider': self,
        }
        return template.render(ctx)

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

    @transaction.atomic()
    def execute_refund(self, refund: OrderRefund):
        self._init_api()

        payment_info = refund.payment.info_data
        OrderPayment.objects.select_for_update(of=OF_SELF).get(pk=refund.payment.pk)

        if not payment_info:
            raise PaymentException(_('No payment information found.'))

        try:
            if payment_info['id'].startswith('pi_'):
                if 'latest_charge' in payment_info and isinstance(payment_info.get("latest_charge"), dict):
                    chargeid = payment_info['latest_charge']['id']
                else:
                    chargeid = payment_info['charges']['data'][0]['id']
            else:
                chargeid = payment_info['id']

            kwargs = {}
            if self.settings.connect_destination:
                kwargs['reverse_transfer'] = True
            r = stripe.Refund.create(
                charge=chargeid,
                amount=self._get_amount(refund),
                **self.api_kwargs,
                **kwargs,
            )
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

    def shred_payment_info(self, obj: OrderPayment):
        if not obj.info:
            return
        d = json.loads(obj.info)

        keys = (
            'amount', 'currency', 'status', 'id', 'amount_capturable', 'amount_details', 'amount_received',
            'application', 'application_fee_amount', 'canceled_at', 'confirmation_method', 'created', 'description',
            'last_payment_error', 'payment_method', 'statement_descriptor', 'livemode'
        )
        new = {k: v for k, v in d.items() if k in keys}

        if d.get("latest_charge") and not isinstance(d["latest_charge"], str):
            keys = (
                'amount', 'amount_captured', 'amount_refunded', 'application', 'application_fee_amount',
                'balance_transaction', 'captured', 'created', 'currency', 'description', 'destination',
                'disputed', 'failure_balance_transaction', 'failure_code', 'failure_message', 'id',
                'livemode', 'metadata', 'object', 'on_behalf_of', 'outcome', 'paid', 'payment_intent',
                'payment_method', 'receipt_url', 'refunded', 'status', 'transfer_data', 'transfer_group',
            )
            new["latest_charge"] = {k: v for k, v in d["latest_charge"].items() if k in keys}

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
                    'country': d['source'].get('card', {}).get('country'),
                    'last4': d['source'].get('card', {}).get('last4'),
                }
            }

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
            if 'payment_stripe_{}_payment_method_id'.format(self.method) in request.session:
                del request.session['payment_stripe_{}_payment_method_id'.format(self.method)]

    def is_moto(self, request, payment=None) -> bool:
        return False

    def _payment_intent_kwargs(self, request, payment):
        return {}

    def _handle_payment_intent(self, request, payment, intent=None):
        self._init_api()

        try:
            if self.payment_is_valid_session(request):
                payment_method_id = request.session.get('payment_stripe_{}_payment_method_id'.format(self.method), None)
                idempotency_key_seed = payment_method_id if payment_method_id is not None else payment.full_id

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

                if self.method == "card":
                    params['statement_descriptor_suffix'] = self.statement_descriptor(payment)
                else:
                    params['statement_descriptor'] = self.statement_descriptor(payment)

                intent = stripe.PaymentIntent.create(
                    amount=self._get_amount(payment),
                    currency=self.event.currency.lower(),
                    payment_method=payment_method_id,
                    payment_method_types=[self.method],
                    confirmation_method=self.confirmation_method,
                    confirm=True,
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
                    idempotency_key=str(self.event.id) + payment.order.code + idempotency_key_seed,
                    return_url=build_absolute_uri(self.event, 'plugins:stripe:sca.return', kwargs={
                        'order': payment.order.code,
                        'payment': payment.pk,
                        'hash': payment.order.tagged_secret('plugins:stripe'),
                    }),
                    expand=['latest_charge'],
                    **params
                )
            else:
                payment_info = json.loads(payment.info)

                if 'id' in payment_info:
                    if not intent:
                        intent = stripe.PaymentIntent.retrieve(
                            payment_info['id'],
                            expand=["latest_charge"],
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
                if intent.next_action.type == 'multibanco_display_details':
                    payment.state = OrderPayment.PAYMENT_STATE_PENDING
                    payment.save()
                    return

                payment.state = OrderPayment.PAYMENT_STATE_CREATED
                payment.save()
                return self._redirect_to_sca(request, payment)

            if intent.status == 'requires_action':
                payment.info = str(intent)
                payment.state = OrderPayment.PAYMENT_STATE_CREATED
                payment.save()
                return self._redirect_to_sca(request, payment)

            if intent.status == 'requires_confirmation':
                payment.info = str(intent)
                payment.state = OrderPayment.PAYMENT_STATE_CREATED
                payment.save()
                self._confirm_payment_intent(request, payment)

            elif intent.status == 'succeeded' and intent.latest_charge.paid:
                try:
                    payment.info = str(intent)
                    payment.confirm()
                except Quota.QuotaExceededException as e:
                    raise PaymentException(str(e))
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

    def _redirect_to_sca(self, request, payment):
        url = build_absolute_uri(self.event, 'plugins:stripe:sca', kwargs={
            'order': payment.order.code,
            'payment': payment.pk,
            'hash': payment.order.tagged_secret('plugins:stripe'),
        })
        if not self.redirect_in_widget_allowed and request.session.get('iframe_session', False):
            return build_absolute_uri(self.event, 'plugins:stripe:redirect') + '?data=' + signing.dumps({
                'url': url,
                'session': {},
            }, salt='safe-redirect')

        return url

    def _confirm_payment_intent(self, request, payment):
        self._init_api()

        try:
            payment_info = json.loads(payment.info)

            intent = stripe.PaymentIntent.confirm(
                payment_info['id'],
                return_url=build_absolute_uri(self.event, 'plugins:stripe:sca.return', kwargs={
                    'order': payment.order.code,
                    'payment': payment.pk,
                    'hash': payment.order.tagged_secret('plugins:stripe'),
                }),
                expand=["latest_charge"],
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


class StripeRedirectMethod(StripeMethod):
    redirect_action_handling = "redirect"

    def payment_is_valid_session(self, request):
        # This does not have a payment_method_id, so we set it manually to None during checkout.
        # But we still need to check for its presence here.
        if "payment_stripe_{}_payment_method_id".format(self.method) in request.session:
            return True
        return False

    def checkout_prepare(self, request, cart):
        # This does not have a payment_method_id, so we set it manually to None during checkout, so that we can
        # verify later on if we are in or outside the checkout process.
        request.session["payment_stripe_{}_payment_method_id".format(self.method)] = None
        return True

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": self.method,
            }
        }

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple_noform.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'explanation': self.explanation,
        }
        return template.render(ctx)


class StripeCC(StripeMethod):
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
            'explanation': self.explanation,
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
            return moto and payment.order.sales_channel.identifier == 'resellers'

        return moto

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            if "latest_charge" in pi and isinstance(pi.get("latest_charge"), dict):
                card = pi["latest_charge"]["payment_method_details"]["card"]
            else:
                card = pi["source"]["card"]
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)
        return f'{self.public_name}: ' \
               f'{card.get("brand", "").title()} ' \
               f'************{card.get("last4", "****")}, ' \
               f'{_("expires {month}/{year}").format(month=card.get("exp_month"), year=card.get("exp_year"))}'


class StripeSEPADirectDebit(StripeMethod):
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
            'explanation': self.explanation,
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
            return super().execute_payment(request, payment)
        finally:
            fields = ['accountname', 'line1', 'postal_code', 'city', 'country']
            for field in fields:
                if 'payment_stripe_sepa_debit_{}'.format(field) in request.session:
                    del request.session['payment_stripe_sepa_debit_{}'.format(field)]


class StripeAffirm(StripeMethod):
    identifier = 'stripe_affirm'
    verbose_name = _('Affirm via Stripe')
    public_name = _('Affirm')
    method = 'affirm'
    redirect_action_handling = 'redirect'

    def payment_is_valid_session(self, request):
        # Affirm does not have a payment_method_id, so we set it manually to None during checkout.
        # But we still need to check for its presence here.
        if 'payment_stripe_{}_payment_method_id'.format(self.method) in request.session:
            return True
        return False

    def checkout_prepare(self, request, cart):
        # Affirm does not have a payment_method_id, so we set it manually to None during checkout, so that we can
        # verify later on if we are in or outside the checkout process.
        request.session['payment_stripe_{}_payment_method_id'.format(self.method)] = None
        return True

    def is_allowed(self, request: HttpRequest, total: Decimal=None) -> bool:
        return Decimal(50.00) <= total <= Decimal(30000.00) and super().is_allowed(request, total)

    def order_change_allowed(self, order: Order, request: HttpRequest=None) -> bool:
        return Decimal(50.00) <= order.pending_sum <= Decimal(30000.00) and super().order_change_allowed(order, request)

    def _payment_intent_kwargs(self, request, payment):
        return {
            'payment_method_data': {
                'type': 'affirm',
            }
        }

    def payment_form_render(self, request, total, order=None) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple_messaging_noform.html')
        ctx = {
            'request': request,
            'event': self.event,
            'total': self._decimal_to_int(total),
            'explanation': self.explanation,
            'method': self.method,
        }
        return template.render(ctx)


class StripeKlarna(StripeRedirectMethod):
    identifier = "stripe_klarna"
    verbose_name = _("Klarna via Stripe")
    public_name = _("Klarna")
    method = "klarna"
    allowed_countries = {"US", "CA", "AU", "NZ", "GB", "IE", "FR", "ES", "DE", "AT", "BE", "DK", "FI", "IT", "NL", "NO", "SE"}
    redirect_in_widget_allowed = False

    def _detect_country(self, request, order=None):
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

        ia = get_invoice_address()
        country = None
        if ia.country:
            country = str(ia.country)
        if country not in self.allowed_countries:
            country = guess_country_from_request(request, self.event)
        if country not in self.allowed_countries:
            country = self.settings.merchant_country
        if country not in self.allowed_countries:
            country = "DE"
        return country

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "klarna",
                "billing_details": {
                    "email": payment.order.email,
                    "address": {
                        "country": self._detect_country(request, payment.order),
                    },
                },
            }
        }

    def payment_form_render(self, request, total, order=None) -> str:
        template = get_template(
            "pretixplugins/stripe/checkout_payment_form_simple_messaging_noform.html"
        )
        ctx = {
            "request": request,
            "event": self.event,
            "total": self._decimal_to_int(total),
            "method": self.method,
            'explanation': self.explanation,
            "country": self._detect_country(request, order)
        }
        return template.render(ctx)

    def test_mode_message(self):
        if self.settings.connect_client_id and not self.settings.secret_key:
            is_testmode = True
        else:
            is_testmode = (
                self.settings.secret_key and "_test_" in self.settings.secret_key
            )
        if is_testmode:
            return mark_safe(
                _(
                    "The Stripe plugin is operating in test mode. You can use one of <a {args}>many test "
                    "cards</a> to perform a transaction. No money will actually be transferred."
                ).format(
                    args='href="https://docs.klarna.com/resources/test-environment/sample-customer-data/" target="_blank"'
                )
            )
        return None


class StripeRedirectWithAccountNamePaymentIntentMethod(StripeRedirectMethod):

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'explanation': self.explanation,
            'form': self.payment_form(request)
        }
        return template.render(ctx)

    @property
    def payment_form_fields(self):
        return OrderedDict([
            ('account', forms.CharField(label=_('Account holder'))),
        ])

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        try:
            return super().execute_payment(request, payment)
        finally:
            if f'payment_stripe_{self.method}_account' in request.session:
                del request.session[f'payment_stripe_{self.method}_account']

    def checkout_prepare(self, request, cart):
        form = self.payment_form(request)
        if form.is_valid():
            request.session[f"payment_stripe_{self.method}_payment_method_id"] = None
            request.session[f'payment_stripe_{self.method}_account'] = form.cleaned_data['account']
            return True
        return False


class StripeGiropay(StripeRedirectWithAccountNamePaymentIntentMethod):
    identifier = 'stripe_giropay'
    verbose_name = _('giropay via Stripe')
    public_name = _('giropay')
    method = 'giropay'
    explanation = _(
        'giropay is an online payment method available to all customers of most German banks, usually after one-time '
        'activation. Please keep your online banking account and login information available.'
    )
    redirect_in_widget_allowed = False

    def is_allowed(self, request: HttpRequest, total: Decimal=None) -> bool:
        # Stripe<>giropay is shut down July 1st
        return super().is_allowed(request, total) and now() < datetime(
            2024, 7, 1, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Berlin")
        )

    def order_change_allowed(self, order: Order, request: HttpRequest=None) -> bool:
        return super().order_change_allowed(order, request) and now() < datetime(
            2024, 7, 1, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Berlin")
        )

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "giropay",
                "giropay": {},
                "billing_details": {
                    "name": request.session.get(f"payment_stripe_{self.method}_account") or gettext("unknown name")
                },
            }
        }

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            return gettext('Bank account at {bank}').format(
                bank=(
                    pi.get("latest_charge", {}).get("payment_method_details", {}).get("giropay", {}).get("bank_name") or
                    pi.get("source", {}).get("giropay", {}).get("bank_name", "?")
                )
            )
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)


class StripeIdeal(StripeRedirectMethod):
    identifier = 'stripe_ideal'
    verbose_name = _('iDEAL via Stripe')
    public_name = _('iDEAL')
    method = 'ideal'
    explanation = _(
        'iDEAL is an online payment method available to customers of Dutch banks. Please keep your online '
        'banking account and login information available.'
    )
    redirect_in_widget_allowed = False

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            return gettext('Bank account at {bank}').format(
                bank=(
                    pi.get("latest_charge", {}).get("payment_method_details", {}).get("ideal", {}).get("bank") or
                    pi.get("source", {}).get("ideal", {}).get("bank", "?")
                ).replace("_", " ").title()
            )
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)


class StripeAlipay(StripeRedirectMethod):
    identifier = 'stripe_alipay'
    verbose_name = _('Alipay via Stripe')
    public_name = _('Alipay')
    method = 'alipay'
    confirmation_method = 'automatic'
    explanation = _(
        'This payment method is available to customers of the Chinese payment system Alipay. Please keep '
        'your login information available.'
    )


class StripeBancontact(StripeRedirectWithAccountNamePaymentIntentMethod):
    identifier = 'stripe_bancontact'
    verbose_name = _('Bancontact via Stripe')
    public_name = _('Bancontact')
    method = 'bancontact'
    redirect_in_widget_allowed = False

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "bancontact",
                "billing_details": {
                    "name": request.session.get(f"payment_stripe_{self.method}_account") or gettext("unknown name")
                },
            }
        }

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            return gettext('Bank account at {bank}').format(
                bank=(
                    pi.get("latest_charge", {}).get("payment_method_details", {}).get("bancontact", {}).get("bank_name") or
                    pi.get("source", {}).get("bancontact", {}).get("bank_name", "?")
                )
            )
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)


class StripeSofort(StripeRedirectMethod):
    identifier = 'stripe_sofort'
    verbose_name = _('SOFORT via Stripe')
    public_name = _('SOFORT (instant bank transfer)')
    method = 'sofort'
    redirect_in_widget_allowed = False

    def is_allowed(self, request: HttpRequest, total: Decimal=None) -> bool:
        # Stripe<>Sofort is shut down November 29th
        return super().is_allowed(request, total) and now() < datetime(
            2024, 11, 29, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Berlin")
        )

    def order_change_allowed(self, order: Order, request: HttpRequest=None) -> bool:
        return super().order_change_allowed(order, request) and now() < datetime(
            2024, 11, 29, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Berlin")
        )

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'explanation': self.explanation,
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

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "sofort",
                "sofort": {
                    "country": (request.session.get(f"payment_stripe_{self.method}_bank_country") or "DE").upper()
                },
            }
        }

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        try:
            return super().execute_payment(request, payment)
        finally:
            if f'payment_stripe_{self.method}_bank_country' in request.session:
                del request.session[f'payment_stripe_{self.method}_bank_country']

    def payment_is_valid_session(self, request):
        return (
            request.session.get(f'payment_stripe_{self.method}_bank_country', '') != ''
        )

    def checkout_prepare(self, request, cart):
        form = self.payment_form(request)
        if form.is_valid():
            request.session[f'payment_stripe_{self.method}_bank_country'] = form.cleaned_data['bank_country']
            return True
        return False

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


class StripeEPS(StripeRedirectWithAccountNamePaymentIntentMethod):
    identifier = 'stripe_eps'
    verbose_name = _('EPS via Stripe')
    public_name = _('EPS')
    method = 'eps'
    redirect_in_widget_allowed = False

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "eps",
                "billing_details": {
                    "name": request.session.get(f"payment_stripe_{self.method}_account") or gettext("unknown name")
                },
            }
        }

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            return gettext('Bank account at {bank}').format(
                bank=(
                    pi.get("latest_charge", {}).get("payment_method_details", {}).get("eps", {}).get("bank") or
                    pi.get("source", {}).get("eps", {}).get("bank", "?")
                ).replace("_", " ").title()
            )
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)


class StripeMultibanco(StripeRedirectMethod):
    identifier = 'stripe_multibanco'
    verbose_name = _('Multibanco via Stripe')
    public_name = _('Multibanco')
    method = 'multibanco'
    explanation = _(
        'Multibanco is a payment method available to Portuguese bank account holders.'
    )
    redirect_in_widget_allowed = False
    abort_pending_allowed = True

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "multibanco",
                "billing_details": {
                    "email": payment.order.email,
                }
            }
        }


class StripePrzelewy24(StripeRedirectMethod):
    identifier = 'stripe_przelewy24'
    verbose_name = _('Przelewy24 via Stripe')
    public_name = _('Przelewy24')
    method = 'p24'
    explanation = _(
        'Przelewy24 is an online payment method available to customers of Polish banks. Please keep your online '
        'banking account and login information available.'
    )
    redirect_in_widget_allowed = False

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "p24",
                "billing_details": {
                    "email": payment.order.email
                },
            }
        }

    @property
    def is_enabled(self) -> bool:
        return self.settings.get('_enabled', as_type=bool) and self.settings.get('method_przelewy24', as_type=bool)

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        try:
            return gettext('Bank account at {bank}').format(
                bank=(
                    pi.get("latest_charge", {}).get("payment_method_details", {}).get("p24", {}).get("bank") or
                    pi.get("source", {}).get("p24", {}).get("bank", "?")
                ).replace("_", " ").title()
            )
        except:
            logger.exception('Could not parse payment data')
            return super().payment_presale_render(payment)


class StripeWeChatPay(StripeRedirectMethod):
    identifier = 'stripe_wechatpay'
    verbose_name = _('WeChat Pay via Stripe')
    public_name = _('WeChat Pay')
    method = 'wechat_pay'
    confirmation_method = 'automatic'
    explanation = _(
        'This payment method is available to users of the Chinese app WeChat. Please keep your login information '
        'available.'
    )

    @property
    def is_enabled(self) -> bool:
        return self.settings.get('_enabled', as_type=bool) and self.settings.get('method_wechatpay', as_type=bool)

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "wechat_pay",
            },
            "payment_method_options": {
                "wechat_pay": {
                    "client": "web"
                },
            }
        }


class StripeRevolutPay(StripeRedirectMethod):
    identifier = 'stripe_revolut_pay'
    verbose_name = _('Revolut Pay via Stripe')
    public_name = _('Revolut Pay')
    method = 'revolut_pay'
    confirmation_method = 'automatic'
    explanation = _(
        'This payment method is available to users of the Revolut app. Please keep your login information '
        'available.'
    )

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "revolut_pay",
            },
        }


class StripePayByBank(StripeRedirectMethod):
    identifier = 'stripe_pay_by_bank'
    verbose_name = _('Pay by bank via Stripe')
    public_name = _('Pay by bank')
    method = 'pay_by_bank'
    redirect_in_widget_allowed = False
    confirmation_method = 'automatic'
    explanation = _(
        'Pay by bank allows you to authorize a secure Open Banking payment from your banking app. Currently available '
        'only with a UK bank account.'
    )

    def is_allowed(self, request: HttpRequest, total: Decimal=None) -> bool:
        return super().is_allowed(request, total) and self.event.currency == 'GBP'

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "pay_by_bank",
                "billing_details": {
                    "email": payment.order.email,
                },
            },
        }


class StripePayPal(StripeRedirectMethod):
    identifier = 'stripe_paypal'
    verbose_name = _('PayPal via Stripe')
    public_name = _('PayPal')
    method = 'paypal'
    redirect_in_widget_allowed = False


class StripeSwish(StripeRedirectMethod):
    identifier = 'stripe_swish'
    verbose_name = _('Swish via Stripe')
    public_name = _('Swish')
    method = 'swish'
    confirmation_method = 'automatic'
    explanation = _(
        'This payment method is available to users of the Swedish apps Swish and BankID. Please have your app '
        'ready.'
    )

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "swish",
            },
            "payment_method_options": {
                "swish": {
                    "reference": payment.order.full_code,
                },
            }
        }


class StripePromptPay(StripeRedirectMethod):
    identifier = 'stripe_promptpay'
    verbose_name = _('PromptPay via Stripe')
    public_name = 'PromptPay'
    method = 'promptpay'
    confirmation_method = 'automatic'
    explanation = _(
        'This payment method is available to PromptPay users in Thailand. Please have your app ready.'
    )

    def is_allowed(self, request: HttpRequest, total: Decimal=None) -> bool:
        return super().is_allowed(request, total) and request.event.currency == "THB"

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "promptpay",
                "billing_details": {
                    "email": payment.order.email,
                },
            },
        }


class StripeTwint(StripeRedirectMethod):
    identifier = 'stripe_twint'
    verbose_name = _('TWINT via Stripe')
    public_name = 'TWINT'
    method = 'twint'
    confirmation_method = 'automatic'
    explanation = _(
        'This payment method is available to users of the Swiss app TWINT. Please have your app '
        'ready.'
    )

    def is_allowed(self, request: HttpRequest, total: Decimal=None) -> bool:
        return super().is_allowed(request, total) and request.event.currency == "CHF" and total <= Decimal("5000.00")

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "twint",
            },
        }


class StripeMobilePay(StripeRedirectMethod):
    identifier = 'stripe_mobilepay'
    verbose_name = 'MobilePay via Stripe'
    public_name = 'MobilePay'
    method = 'mobilepay'
    confirmation_method = 'automatic'
    explanation = _(
        'This payment method is available to MobilePay app users in Denmark and Finland. Please have your app ready.'
    )

    def _payment_intent_kwargs(self, request, payment):
        return {
            "payment_method_data": {
                "type": "mobilepay",
            },
        }
