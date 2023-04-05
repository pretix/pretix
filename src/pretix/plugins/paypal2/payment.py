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
import hashlib
import json
import logging
import urllib.parse
from collections import OrderedDict
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest
from django.template.loader import get_template
from django.templatetags.static import static
from django.urls import resolve, reverse
from django.utils.crypto import get_random_string
from django.utils.safestring import mark_safe
from django.utils.timezone import now
from django.utils.translation import gettext as __, gettext_lazy as _
from django_countries import countries
from i18nfield.strings import LazyI18nString
from paypalcheckoutsdk.orders import (
    OrdersCaptureRequest, OrdersCreateRequest, OrdersGetRequest,
    OrdersPatchRequest,
)
from paypalcheckoutsdk.payments import CapturesRefundRequest, RefundsGetRequest
from paypalhttp import HttpError

from pretix.base.decimal import round_decimal
from pretix.base.forms.questions import guess_country
from pretix.base.models import Event, Order, OrderPayment, OrderRefund, Quota
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.services.mail import SendMailException
from pretix.base.settings import SettingsSandbox
from pretix.helpers.urls import build_absolute_uri as build_global_uri
from pretix.multidomain.urlreverse import build_absolute_uri, eventreverse
from pretix.plugins.paypal2.client.core.environment import (
    LiveEnvironment, SandboxEnvironment,
)
from pretix.plugins.paypal2.client.core.paypal_http_client import (
    PayPalHttpClient,
)
from pretix.plugins.paypal2.client.customer.partner_referral_create_request import (
    PartnerReferralCreateRequest,
)
from pretix.plugins.paypal.models import ReferencedPayPalObject

logger = logging.getLogger('pretix.plugins.paypal2')

SUPPORTED_CURRENCIES = ['AUD', 'BRL', 'CAD', 'CZK', 'DKK', 'EUR', 'HKD', 'HUF', 'INR', 'ILS', 'JPY', 'MYR', 'MXN',
                        'TWD', 'NZD', 'NOK', 'PHP', 'PLN', 'GBP', 'RUB', 'SGD', 'SEK', 'CHF', 'THB', 'USD']

LOCAL_ONLY_CURRENCIES = ['INR']


class PaypalSettingsHolder(BasePaymentProvider):
    identifier = 'paypal_settings'
    verbose_name = _('PayPal')
    is_enabled = False
    is_meta = True
    payment_form_fields = OrderedDict([])

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('payment', 'paypal', event)

    @property
    def settings_form_fields(self):
        # ISU
        if self.settings.connect_client_id and self.settings.connect_secret_key and not self.settings.secret:
            if self.settings.isu_merchant_id:
                fields = [
                    ('isu_merchant_id',
                     forms.CharField(
                         label=_('PayPal Merchant ID'),
                         disabled=True
                     )),
                ]
            else:
                return {}
        # Manual API integration
        else:
            fields = [
                ('client_id',
                 forms.CharField(
                     label=_('Client ID'),
                     max_length=80,
                     min_length=80,
                     help_text=_('<a target="_blank" rel="noopener" href="{docs_url}">{text}</a>').format(
                         text=_('Click here for a tutorial on how to obtain the required keys'),
                         docs_url='https://docs.pretix.eu/en/latest/user/payments/paypal.html'
                     )
                 )),
                ('secret',
                 forms.CharField(
                     label=_('Secret'),
                     max_length=80,
                     min_length=80,
                 )),
                ('endpoint',
                 forms.ChoiceField(
                     label=_('Endpoint'),
                     initial='live',
                     choices=(
                         ('live', 'Live'),
                         ('sandbox', 'Sandbox'),
                     ),
                 )),
            ]

        methods = [
            ('method_wallet',
             forms.BooleanField(
                 label=_('PayPal'),
                 required=False,
                 help_text=_(
                     'Even if a customer chooses an Alternative Payment Method, they will always have the option to '
                     'revert back to paying with their PayPal account. For this reason, this payment method is always '
                     'active.'
                 ),
                 disabled=True,
             )),
            ('method_apm',
             forms.BooleanField(
                 label=_('Alternative Payment Methods'),
                 help_text=_(
                     'In addition to payments through a PayPal account, you can also offer your customers the option '
                     'to pay with credit cards and other, local payment methods such as SOFORT, giropay, iDEAL, and '
                     'many more - even when they do not have a PayPal account. Eligible payment methods will be '
                     'determined based on the shoppers location. For German merchants, this is the direct successor '
                     'of PayPal Plus.'
                 ),
                 required=False,
                 widget=forms.CheckboxInput(
                     attrs={
                         'data-checkbox-dependency': '#id_payment_paypal_method_wallet',
                     }
                 )
             )),
            ('disable_method_sepa',
             forms.BooleanField(
                 label=_('Disable SEPA Direct Debit'),
                 help_text=_(
                     'While most payment methods cannot be recalled by a customer without outlining their exact grief '
                     'with the merchants, SEPA Direct Debit can be recalled with the press of a button. For that '
                     'reason - and depending on the nature of your event - you might want to disabled the option of '
                     'SEPA Direct Debit payments in order to reduce the risk of costly chargebacks.'
                 ),
                 required=False,
                 widget=forms.CheckboxInput(
                     attrs={
                         'data-checkbox-dependency': '#id_payment_paypal_method_apm',
                     }
                 )
             )),
            ('enable_method_paylater',
             forms.BooleanField(
                 label=_('Enable Buy Now Pay Later'),
                 help_text=_(
                     'Offer your customers the possibility to buy now (up to a certain limit) and pay in multiple installments '
                     'or within 30 days. You, as the merchant, are getting your money right away.'
                 ),
                 required=False,
                 widget=forms.CheckboxInput(
                     attrs={
                         'data-checkbox-dependency': '#id_payment_paypal_method_apm',
                     }
                 )
             )),

        ]

        extra_fields = [
            ('prefix',
             forms.CharField(
                 label=_('Reference prefix'),
                 help_text=_('Any value entered here will be added in front of the regular booking reference '
                             'containing the order number.'),
                 required=False,
             )),
            ('postfix',
             forms.CharField(
                 label=_('Reference postfix'),
                 help_text=_('Any value entered here will be added behind the regular booking reference '
                             'containing the order number.'),
                 required=False,
             )),
        ]

        if settings.DEBUG:
            allcountries = list(countries)
            allcountries.insert(0, ('', _('-- Automatic --')))

            extra_fields.append(
                ('debug_buyer_country',
                 forms.ChoiceField(
                     choices=allcountries,
                     label=mark_safe('<span class="label label-primary">DEBUG</span> {}'.format(_('Buyer country'))),
                     initial=guess_country(self.event),
                 )),
            )

        d = OrderedDict(
            fields + methods + extra_fields + list(super().settings_form_fields.items())
        )

        d.move_to_end('prefix')
        d.move_to_end('postfix')
        d.move_to_end('_enabled', False)
        return d

    def settings_content_render(self, request):
        settings_content = ""
        if self.settings.connect_client_id and self.settings.connect_secret_key and not self.settings.secret:
            # Use ISU
            if not self.settings.isu_merchant_id:
                isu_referral_url = self.get_isu_referral_url(request)
                settings_content = (
                    "<p>{}</p>"
                    "<a href='{}' class='btn btn-primary btn-lg {}'>{}</a>"
                ).format(
                    _('To accept payments via PayPal, you will need an account at PayPal. By clicking on the '
                      'following button, you can either create a new PayPal account or connect pretix to an existing '
                      'one.'),
                    isu_referral_url,
                    'disabled' if not isu_referral_url else '',
                    _('Connect with {icon} PayPal').format(icon='<i class="fa fa-paypal"></i>')
                )
            else:
                settings_content = (
                    "<button formaction='{}' class='btn btn-danger'>{}</button>"
                ).format(
                    reverse('plugins:paypal2:isu.disconnect', kwargs={
                        'organizer': self.event.organizer.slug,
                        'event': self.event.slug,
                    }),
                    _('Disconnect from PayPal')
                )
        else:
            settings_content = "<div class='alert alert-info'>%s<br /><code>%s</code></div>" % (
                _('Please configure a PayPal Webhook to the following endpoint in order to automatically cancel orders '
                  'when payments are refunded externally.'),
                build_global_uri('plugins:paypal2:webhook')
            )

        if self.event.currency not in SUPPORTED_CURRENCIES:
            settings_content += (
                '<br><br><div class="alert alert-warning">%s '
                '<a href="https://developer.paypal.com/docs/api/reference/currency-codes/">%s</a>'
                '</div>'
            ) % (
                _("PayPal does not process payments in your event's currency."),
                _("Please check this PayPal page for a complete list of supported currencies.")
            )

        if self.event.currency in LOCAL_ONLY_CURRENCIES:
            settings_content += '<br><br><div class="alert alert-warning">%s''</div>' % (
                _("Your event's currency is supported by PayPal as a payment and balance currency for in-country "
                  "accounts only. This means, that the receiving as well as the sending PayPal account must have been "
                  "created in the same country and use the same currency. Out of country accounts will not be able to "
                  "send any payments.")
            )

        return settings_content

    def get_isu_referral_url(self, request):
        pprov = PaypalMethod(request.event)
        pprov.init_api()

        request.session['payment_paypal_isu_event'] = request.event.pk
        request.session['payment_paypal_isu_tracking_id'] = get_random_string(length=127)

        try:
            req = PartnerReferralCreateRequest()

            req.request_body({
                "operations": [
                    {
                        "operation": "API_INTEGRATION",
                        "api_integration_preference": {
                            "rest_api_integration": {
                                "integration_method": "PAYPAL",
                                "integration_type": "THIRD_PARTY",
                                "third_party_details": {
                                    "features": [
                                        "PAYMENT",
                                        "REFUND",
                                        "ACCESS_MERCHANT_INFORMATION"
                                    ],
                                }
                            }
                        }
                    }
                ],
                "products": [
                    "EXPRESS_CHECKOUT"
                ],
                "partner_config_override": {
                    "partner_logo_url": urllib.parse.urljoin(settings.SITE_URL, static('pretixbase/img/pretix-logo.svg')),
                    "return_url": build_global_uri('plugins:paypal2:isu.return', kwargs={
                        'organizer': self.event.organizer.slug,
                        'event': self.event.slug,
                    })
                },
                "tracking_id": request.session['payment_paypal_isu_tracking_id'],
                "preferred_language_code": request.user.locale.split('-')[0]
            })
            response = pprov.client.execute(req)
        except IOError as e:
            messages.error(request, _('An error occurred during connecting with PayPal, please try again.'))
            logger.exception('PayPal PartnerReferralCreateRequest: {}'.format(str(e)))
        else:
            return self.get_link(response.result.links, 'action_url').href

    def get_link(self, links, rel):
        for link in links:
            if link.rel == rel:
                return link

        return None


class PaypalMethod(BasePaymentProvider):
    identifier = ''
    method = ''
    BN = 'ramiioGmbH_Cart_PPCP'

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('payment', 'paypal', event)

    @property
    def settings_form_fields(self):
        return {}

    @property
    def is_enabled(self) -> bool:
        if self.settings.connect_client_id and self.settings.connect_secret_key and not self.settings.secret:
            if not self.settings.isu_merchant_id:
                return False
        return self.settings.get('_enabled', as_type=bool) and self.settings.get('method_{}'.format(self.method),
                                                                                 as_type=bool)

    @property
    def test_mode_message(self):
        if self.settings.connect_client_id and not self.settings.secret:
            # in OAuth mode, sandbox mode needs to be set global
            is_sandbox = self.settings.connect_endpoint == 'sandbox'
        else:
            is_sandbox = self.settings.get('endpoint') == 'sandbox'
        if is_sandbox:
            return _('The PayPal sandbox is being used, you can test without actually sending money but you will need a '
                     'PayPal sandbox user to log in.')
        return None

    def is_allowed(self, request: HttpRequest, total: Decimal = None) -> bool:
        return super().is_allowed(request, total) and self.event.currency in SUPPORTED_CURRENCIES

    def init_api(self):
        # ISU
        if self.settings.connect_client_id and not self.settings.secret:
            if 'sandbox' in self.settings.connect_endpoint:
                env = SandboxEnvironment(
                    client_id=self.settings.connect_client_id,
                    client_secret=self.settings.connect_secret_key,
                    merchant_id=self.settings.get('isu_merchant_id', None),
                    partner_id=self.BN
                )
            else:
                env = LiveEnvironment(
                    client_id=self.settings.connect_client_id,
                    client_secret=self.settings.connect_secret_key,
                    merchant_id=self.settings.get('isu_merchant_id', None),
                    partner_id=self.BN
                )
        # Manual API integration
        else:
            if 'sandbox' in self.settings.get('endpoint'):
                env = SandboxEnvironment(
                    client_id=self.settings.get('client_id'),
                    client_secret=self.settings.get('secret'),
                    merchant_id=None,
                    partner_id=self.BN
                )
            else:
                env = LiveEnvironment(
                    client_id=self.settings.get('client_id'),
                    client_secret=self.settings.get('secret'),
                    merchant_id=None,
                    partner_id=self.BN
                )

        self.client = PayPalHttpClient(env)

    def payment_is_valid_session(self, request):
        return request.session.get('payment_paypal_oid', '') != ''

    def payment_form_render(self, request) -> str:
        def build_kwargs():
            keys = ['organizer', 'event', 'order', 'secret', 'cart_namespace']
            kwargs = {}
            for key in keys:
                if key in request.resolver_match.kwargs:
                    kwargs[key] = request.resolver_match.kwargs[key]
            return kwargs

        template = get_template('pretixplugins/paypal2/checkout_payment_form.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'method': self.method,
            'xhr': eventreverse(self.event, 'plugins:paypal2:xhr', kwargs=build_kwargs())
        }
        return template.render(ctx)

    def checkout_prepare(self, request, cart):
        paypal_order_id = request.POST.get('payment_paypal_{}_oid'.format(self.method), None)

        # PayPal OID has been previously generated through XHR and onApprove() has fired
        if paypal_order_id and paypal_order_id == request.session.get('payment_paypal_oid', None):
            self.init_api()

            try:
                req = OrdersGetRequest(paypal_order_id)
                response = self.client.execute(req)
            except IOError as e:
                messages.warning(request, _('We had trouble communicating with PayPal'))
                logger.exception('PayPal OrdersGetRequest: {}'.format(str(e)))
                return False
            else:
                if response.result.status == 'APPROVED':
                    return True
            messages.warning(request, _('Something went wrong when requesting the payment status. Please try again.'))
            return False
        # onApprove has fired, but we don't have a matching OID in the session - manipulation/something went wrong.
        elif paypal_order_id:
            messages.warning(request, _('We had trouble communicating with PayPal'))
            return False
        else:
            # We don't have an XHR-generated OID, nor a onApprove-fired OID.
            # Probably no active JavaScript; this won't work
            messages.warning(request, _('You may need to enable JavaScript for PayPal payments.'))
            return False

    def format_price(self, value):
        return str(round_decimal(value, self.event.currency, {
            # PayPal behaves differently than Stripe in deciding what currencies have decimal places
            # Source https://developer.paypal.com/docs/classic/api/currency_codes/
            'HUF': 0,
            'JPY': 0,
            'MYR': 0,
            'TWD': 0,
            # However, CLPs are not listed there while PayPal requires us not to send decimal places there. WTF.
            'CLP': 0,
            # Let's just guess that the ones listed here are 0-based as well
            # https://developers.braintreepayments.com/reference/general/currencies
            'BIF': 0,
            'DJF': 0,
            'GNF': 0,
            'KMF': 0,
            'KRW': 0,
            'LAK': 0,
            'PYG': 0,
            'RWF': 0,
            'UGX': 0,
            'VND': 0,
            'VUV': 0,
            'XAF': 0,
            'XOF': 0,
            'XPF': 0,
        }))

    @property
    def abort_pending_allowed(self):
        return False

    def _create_paypal_order(self, request, payment=None, cart_total=None):
        self.init_api()
        kwargs = {}
        if request.resolver_match and 'cart_namespace' in request.resolver_match.kwargs:
            kwargs['cart_namespace'] = request.resolver_match.kwargs['cart_namespace']

        # ISU
        if request.event.settings.payment_paypal_isu_merchant_id:
            payee = {
                "merchant_id": request.event.settings.payment_paypal_isu_merchant_id,
            }
        # Manual API integration
        else:
            payee = {}

        if payment and not cart_total:
            value = self.format_price(payment.amount)
            currency = payment.order.event.currency
            description = '{prefix}{orderstring}{postfix}'.format(
                prefix='{} '.format(self.settings.prefix) if self.settings.prefix else '',
                orderstring=__('Order {order} for {event}').format(
                    event=request.event.name,
                    order=payment.order.code
                ),
                postfix=' {}'.format(self.settings.postfix) if self.settings.postfix else ''
            )
            custom_id = '{prefix}{slug}-{code}{postfix}'.format(
                prefix='{} '.format(self.settings.prefix) if self.settings.prefix else '',
                slug=self.event.slug.upper(),
                code=payment.order.code,
                postfix=' {}'.format(self.settings.postfix) if self.settings.postfix else ''
            )
            request.session['payment_paypal_payment'] = payment.pk
        elif cart_total and not payment:
            value = self.format_price(cart_total)
            currency = request.event.currency
            description = __('Event tickets for {event}').format(event=request.event.name)
            custom_id = '{prefix}{slug}{postfix}'.format(
                prefix='{} '.format(self.settings.prefix) if self.settings.prefix else '',
                slug=request.event.slug.upper(),
                postfix=' {}'.format(self.settings.postfix) if self.settings.postfix else ''
            )
            request.session['payment_paypal_payment'] = None
        else:
            pass

        try:
            paymentreq = OrdersCreateRequest()
            paymentreq.request_body({
                'intent': 'CAPTURE',
                # 'payer': {},  # We could transmit PII (email, name, address, etc.)
                'purchase_units': [{
                    'amount': {
                        'currency_code': currency,
                        'value': value,
                    },
                    'payee': payee,
                    'description': description[:127],
                    'custom_id': custom_id[:127],
                    # 'shipping': {},  # Include Shipping information?
                }],
                'application_context': {
                    'locale': request.LANGUAGE_CODE.split('-')[0],
                    'shipping_preference': 'NO_SHIPPING',  # 'SET_PROVIDED_ADDRESS',  # Do not set on non-ship order?
                    'user_action': 'CONTINUE',
                    'return_url': build_absolute_uri(request.event, 'plugins:paypal2:return', kwargs=kwargs),
                    'cancel_url': build_absolute_uri(request.event, 'plugins:paypal2:abort', kwargs=kwargs),
                },
            })
            response = self.client.execute(paymentreq)
        except IOError as e:
            messages.error(request, _('We had trouble communicating with PayPal'))
            logger.exception('PayPal OrdersCreateRequest: {}'.format(str(e)))
        else:
            if response.result.status not in ('CREATED', 'PAYER_ACTION_REQUIRED'):
                messages.error(request, _('We had trouble communicating with PayPal'))
                logger.error('Invalid payment state: ' + str(paymentreq))
                return

            request.session['payment_paypal_oid'] = response.result.id
            return response.result

    def checkout_confirm_render(self, request) -> str:
        """
        Returns the HTML that should be displayed when the user selected this provider
        on the 'confirm order' page.
        """
        template = get_template('pretixplugins/paypal2/checkout_payment_confirm.html')
        ctx = {
            'request': request,
            'url': resolve(request.path_info),
            'event': self.event,
            'settings': self.settings,
            'method': self.method
        }
        return template.render(ctx)

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        try:
            if request.session.get('payment_paypal_oid', '') == '':
                raise PaymentException(_('We were unable to process your payment. See below for details on how to '
                                         'proceed.'))

            if self.settings.connect_client_id and self.settings.connect_secret_key and not self.settings.secret:
                if not self.settings.isu_merchant_id:
                    raise PaymentException('Payment method misconfigured')
            self.init_api()
            try:
                req = OrdersGetRequest(request.session.get('payment_paypal_oid'))
                response = self.client.execute(req)
            except IOError as e:
                logger.exception('PayPal OrdersGetRequest: {}'.format(str(e)))
                raise PaymentException(_('We had trouble communicating with PayPal'))
            else:
                pp_captured_order = response.result

            try:
                ReferencedPayPalObject.objects.get_or_create(order=payment.order, payment=payment, reference=pp_captured_order.id)
            except ReferencedPayPalObject.MultipleObjectsReturned:
                pass
            if str(pp_captured_order.purchase_units[0].amount.value) != str(payment.amount) or \
                    pp_captured_order.purchase_units[0].amount.currency_code != self.event.currency:
                logger.error('Value mismatch: Payment %s vs paypal trans %s' % (payment.id, str(pp_captured_order.dict())))
                raise PaymentException(_('We were unable to process your payment. See below for details on how to '
                                         'proceed.'))

            if pp_captured_order.status == 'APPROVED':
                # We are suspecting that some or even all APMs cannot be PATCHed after being approved by the buyer,
                # without the PayPal Order losing its APPROVED-status again.
                # Since APMs are already created with their proper custom_id and description (at the time the PayPal
                # Order is created for the APM, we already have pretix order code), we skip the PATCH-request.
                if payment.order.code not in pp_captured_order.purchase_units[0].custom_id:
                    try:
                        custom_id = '{prefix}{orderstring}{postfix}'.format(
                            prefix='{} '.format(self.settings.prefix) if self.settings.prefix else '',
                            orderstring=__('Order {slug}-{code}').format(
                                slug=self.event.slug.upper(),
                                code=payment.order.code
                            ),
                            postfix=' {}'.format(self.settings.postfix) if self.settings.postfix else ''
                        )
                        description = '{prefix}{orderstring}{postfix}'.format(
                            prefix='{} '.format(self.settings.prefix) if self.settings.prefix else '',
                            orderstring=__('Order {order} for {event}').format(
                                event=request.event.name,
                                order=payment.order.code
                            ),
                            postfix=' {}'.format(self.settings.postfix) if self.settings.postfix else ''
                        )
                        patchreq = OrdersPatchRequest(pp_captured_order.id)
                        patchreq.request_body([
                            {
                                "op": "replace",
                                "path": "/purchase_units/@reference_id=='default'/custom_id",
                                "value": custom_id[:127],
                            },
                            {
                                "op": "replace",
                                "path": "/purchase_units/@reference_id=='default'/description",
                                "value": description[:127],
                            }
                        ])
                        self.client.execute(patchreq)
                    except IOError as e:
                        messages.error(request, _('We had trouble communicating with PayPal'))
                        logger.exception('PayPal OrdersPatchRequest: {}'.format(str(e)))
                        return

                try:
                    capturereq = OrdersCaptureRequest(pp_captured_order.id)
                    response = self.client.execute(capturereq)
                except HttpError as e:
                    text = _('We were unable to process your payment. See below for details on how to proceed.')
                    try:
                        error = json.loads(e.message)
                    except ValueError:
                        error = {"message": str(e.message)}

                    try:
                        if error["details"][0]["issue"] == "ORDER_ALREADY_CAPTURED":
                            # ignore, do nothing, write nothing, just redirect user to order page, this is likely
                            # a race condition
                            logger.info('PayPal ORDER_ALREADY_CAPTURED, ignoring')
                            return
                        elif error["details"][0]["issue"] == "INSTRUMENT_DECLINED":
                            # Use PayPal's rejection message
                            text = error["details"][0]["description"]
                    except (KeyError, IndexError):
                        pass

                    payment.fail(info={**pp_captured_order.dict(), "error": error}, log_data=error)
                    logger.exception('PayPal OrdersCaptureRequest: {}'.format(str(e)))
                    raise PaymentException(text)
                except IOError as e:
                    payment.fail(info={**pp_captured_order.dict(), "error": {"message": str(e)}}, log_data={"error": str(e)})
                    logger.exception('PayPal OrdersCaptureRequest: {}'.format(str(e)))
                    raise PaymentException(
                        _('We were unable to process your payment. See below for details on how to proceed.')
                    )
                else:
                    pp_captured_order = response.result

                for purchaseunit in pp_captured_order.purchase_units:
                    for capture in purchaseunit.payments.captures:
                        try:
                            ReferencedPayPalObject.objects.get_or_create(order=payment.order, payment=payment, reference=capture.id)
                        except ReferencedPayPalObject.MultipleObjectsReturned:
                            pass

                        if capture.status != 'COMPLETED':
                            messages.warning(request, _('PayPal has not yet approved the payment. We will inform you as '
                                                        'soon as the payment completed.'))
                            payment.info = json.dumps(pp_captured_order.dict())
                            payment.state = OrderPayment.PAYMENT_STATE_PENDING
                            payment.save()
                            return

            payment.refresh_from_db()

            if pp_captured_order.status != 'COMPLETED':
                payment.fail(info=pp_captured_order.dict())
                logger.error('Invalid state: %s' % repr(pp_captured_order.dict()))
                raise PaymentException(
                    _('We were unable to process your payment. See below for details on how to proceed.')
                )

            if payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED:
                logger.warning('PayPal success event even though order is already marked as paid')
                return

            try:
                payment.info = json.dumps(pp_captured_order.dict())
                payment.save(update_fields=['info'])
                payment.confirm()
            except Quota.QuotaExceededException as e:
                raise PaymentException(str(e))

            except SendMailException:
                messages.warning(request, _('There was an error sending the confirmation mail.'))
        finally:
            if 'payment_paypal_oid' in request.session:
                del request.session['payment_paypal_oid']

    def payment_pending_render(self, request, payment) -> str:
        retry = True
        try:
            if (
                    payment.info
                    and payment.info_data['purchase_units'][0]['payments']['captures'][0]['status'] == 'pending'
            ):
                retry = False
        except (KeyError, IndexError):
            pass
        template = get_template('pretixplugins/paypal2/pending.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings,
               'retry': retry, 'order': payment.order}
        return template.render(ctx)

    def matching_id(self, payment: OrderPayment):
        sale_id = None

        # Legacy PayPal info-data
        if 'purchase_units' not in payment.info_data:
            for trans in payment.info_data.get('transactions', []):
                for res in trans.get('related_resources', []):
                    if 'sale' in res and 'id' in res['sale']:
                        sale_id = res['sale']['id']
        else:
            for trans in payment.info_data.get('purchase_units', []):
                for res in trans.get('payments', {}).get('captures', []):
                    sale_id = res['id']

        return sale_id or payment.info_data.get('id', None)

    def api_payment_details(self, payment: OrderPayment):
        sale_id = None

        # Legacy PayPal info-data
        if 'purchase_units' not in payment.info_data:
            for trans in payment.info_data.get('transactions', []):
                for res in trans.get('related_resources', []):
                    if 'sale' in res and 'id' in res['sale']:
                        sale_id = res['sale']['id']

            return {
                "payer_email": payment.info_data.get('payer', {}).get('payer_info', {}).get('email'),
                "payer_id": payment.info_data.get('payer', {}).get('payer_info', {}).get('payer_id'),
                "cart_id": payment.info_data.get('cart', None),
                "payment_id": payment.info_data.get('id', None),
                "sale_id": sale_id,
            }
        else:
            for trans in payment.info_data.get('purchase_units', []):
                for res in trans.get('payments', {}).get('captures', []):
                    sale_id = res['id']

            return {
                "payer_email": payment.info_data.get('payer', {}).get('email_address'),
                "payer_id": payment.info_data.get('payer', {}).get('payer_id'),
                "cart_id": payment.info_data.get('id', None),
                "payment_id": sale_id,
                "sale_id": sale_id,
            }

    def payment_control_render(self, request: HttpRequest, payment: OrderPayment):
        # Legacy PayPal info-data
        if 'purchase_units' not in payment.info_data:
            template = get_template('pretixplugins/paypal2/control_legacy.html')
            sale_id = None
            for trans in payment.info_data.get('transactions', []):
                for res in trans.get('related_resources', []):
                    if 'sale' in res and 'id' in res['sale']:
                        sale_id = res['sale']['id']
            ctx = {'request': request, 'event': self.event, 'settings': self.settings,
                   'payment_info': payment.info_data, 'order': payment.order, 'sale_id': sale_id}
        else:
            template = get_template('pretixplugins/paypal2/control.html')
            ctx = {'request': request, 'event': self.event, 'settings': self.settings,
                   'payment_info': payment.info_data, 'order': payment.order}

        return template.render(ctx)

    def payment_control_render_short(self, payment: OrderPayment) -> str:
        # Legacy PayPal info-data
        if 'purchase_units' not in payment.info_data:
            return payment.info_data.get('payer', {}).get('payer_info', {}).get('email', '')
        else:
            return '{} / {}'.format(
                payment.info_data.get('id', ''),
                payment.info_data.get('payer', {}).get('email_address', '')
            )

    def payment_partial_refund_supported(self, payment: OrderPayment):
        # Paypal refunds are possible for 180 days after purchase:
        # https://www.paypal.com/lc/smarthelp/article/how-do-i-issue-a-refund-faq780#:~:text=Refund%20after%20180%20days%20of,PayPal%20balance%20of%20the%20recipient.
        return (now() - payment.payment_date).days <= 180

    def payment_refund_supported(self, payment: OrderPayment):
        self.payment_partial_refund_supported(payment)

    def execute_refund(self, refund: OrderRefund):
        self.init_api()

        try:
            pp_payment = None
            payment_info_data = None
            # Legacy PayPal - get up to date info data first
            if "purchase_units" not in refund.payment.info_data:
                req = OrdersGetRequest(refund.payment.info_data['cart'])
                response = self.client.execute(req)
                payment_info_data = response.result.dict()
            else:
                payment_info_data = refund.payment.info_data

            for res in payment_info_data['purchase_units'][0]['payments']['captures']:
                if res['status'] in ['COMPLETED', 'PARTIALLY_REFUNDED']:
                    pp_payment = res['id']
                    break

            if not pp_payment:
                req = OrdersGetRequest(payment_info_data['id'])
                response = self.client.execute(req)
                for res in response.result.purchase_units[0].payments.captures:
                    if res['status'] in ['COMPLETED', 'PARTIALLY_REFUNDED']:
                        pp_payment = res.id
                        break

            req = CapturesRefundRequest(pp_payment)
            req.request_body({
                "amount": {
                    "value": self.format_price(refund.amount),
                    "currency_code": refund.order.event.currency
                }
            })
            response = self.client.execute(req)
        except IOError as e:
            refund.order.log_action('pretix.event.order.refund.failed', {
                'local_id': refund.local_id,
                'provider': refund.provider,
                'error': str(e)
            })
            logger.error('execute_refund: {}'.format(str(e)))
            raise PaymentException(_('Refunding the amount via PayPal failed: {}').format(str(e)))

        refund.info = json.dumps(response.result.dict())
        refund.save(update_fields=['info'])

        req = RefundsGetRequest(response.result.id)
        response = self.client.execute(req)
        refund.info = json.dumps(response.result.dict())
        refund.save(update_fields=['info'])

        if response.result.status == 'COMPLETED':
            refund.done()
        elif response.result.status == 'PENDING':
            refund.state = OrderRefund.REFUND_STATE_TRANSIT
            refund.save(update_fields=['state'])
        else:
            refund.order.log_action('pretix.event.order.refund.failed', {
                'local_id': refund.local_id,
                'provider': refund.provider,
                'error': str(response.result.status_details.reason)
            })
            raise PaymentException(_('Refunding the amount via PayPal failed: {}').format(response.result.status_details.reason))

    def payment_prepare(self, request, payment):
        paypal_order_id = request.POST.get('payment_paypal_{}_oid'.format(self.method), None)

        # PayPal OID has been previously generated through XHR and onApprove() has fired
        if paypal_order_id and paypal_order_id == request.session.get('payment_paypal_oid', None):
            self.init_api()

            try:
                req = OrdersGetRequest(paypal_order_id)
                response = self.client.execute(req)
            except IOError as e:
                messages.warning(request, _('We had trouble communicating with PayPal'))
                logger.exception('PayPal OrdersGetRequest: {}'.format(str(e)))
                return False
            else:
                if response.result.status == 'APPROVED':
                    return True
            messages.warning(request, _('Something went wrong when requesting the payment status. Please try again.'))
            return False
        # onApprove has fired, but we don't have a matching OID in the session - manipulation/something went wrong.
        elif paypal_order_id:
            messages.warning(request, _('We had trouble communicating with PayPal'))
            return False
        else:
            # We don't have an XHR-generated OID, nor a onApprove-fired OID.
            # Probably no active JavaScript; this won't work
            messages.warning(request, _('You may need to enable JavaScript for PayPal payments.'))
            return False

    def shred_payment_info(self, obj):
        if obj.info:
            d = json.loads(obj.info)
            new = {
                'id': d.get('id'),
                'payer': {
                    'payer_info': {
                        'email': '█'
                    }
                },
                'update_time': d.get('update_time'),
                'transactions': [
                    {
                        'amount': t.get('amount')
                    } for t in d.get('transactions', [])
                ],
                '_shredded': True
            }
            obj.info = json.dumps(new)
            obj.save(update_fields=['info'])

        for le in obj.order.all_logentries().filter(action_type="pretix.plugins.paypal.event").exclude(data=""):
            d = le.parsed_data
            if 'resource' in d:
                d['resource'] = {
                    'id': d['resource'].get('id'),
                    'sale_id': d['resource'].get('sale_id'),
                    'parent_payment': d['resource'].get('parent_payment'),
                }
            le.data = json.dumps(d)
            le.shredded = True
            le.save(update_fields=['data', 'shredded'])

    def render_invoice_text(self, order: Order, payment: OrderPayment) -> str:
        if order.status == Order.STATUS_PAID:
            if payment.info_data.get('id', None):
                try:
                    return '{}\r\n{}: {}\r\n{}: {}'.format(
                        _('The payment for this invoice has already been received.'),
                        _('PayPal payment ID'),
                        payment.info_data['id'],
                        _('PayPal sale ID'),
                        payment.info_data['transactions'][0]['related_resources'][0]['sale']['id']
                    )
                except (KeyError, IndexError):
                    return '{}\r\n{}: {}'.format(
                        _('The payment for this invoice has already been received.'),
                        _('PayPal payment ID'),
                        payment.info_data['id']
                    )
            else:
                return super().render_invoice_text(order, payment)

        return self.settings.get('_invoice_text', as_type=LazyI18nString, default='')


class PaypalWallet(PaypalMethod):
    identifier = 'paypal'
    verbose_name = _('PayPal')
    public_name = _('PayPal')
    method = 'wallet'


class PaypalAPM(PaypalMethod):
    identifier = 'paypal_apm'
    verbose_name = _('PayPal APM')
    public_name = _('PayPal Alternative Payment Methods')
    method = 'apm'

    def payment_is_valid_session(self, request):
        # Since APMs request the OID by XHR at a later point, no need to check anything here
        return True

    def checkout_prepare(self, request, cart):
        return True

    def payment_prepare(self, request, payment):
        return True

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        # This is a workaround to not have APMs be written to the database with identifier paypal_apm.
        # Since all transactions - APM or not - look the same and are handled the same, we want to keep all PayPal
        # transactions under the "paypal"-identifier - no matter what the customer might have selected.
        payment.provider = "paypal"
        payment.save(update_fields=["provider"])

        paypal_order = self._create_paypal_order(request, payment, None)
        payment.info = json.dumps(paypal_order.dict())
        payment.save(update_fields=['info'])

        return eventreverse(self.event, 'plugins:paypal2:pay', kwargs={
            'order': payment.order.code,
            'payment': payment.pk,
            'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
        })
