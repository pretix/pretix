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
# This file contains Apache-licensed contributions copyrighted by: Jakob Schnell, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
import logging
import urllib.parse
from collections import OrderedDict
from decimal import Decimal

import paypalrestsdk
import paypalrestsdk.exceptions
from django import forms
from django.contrib import messages
from django.core import signing
from django.http import HttpRequest
from django.template.loader import get_template
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext as __, gettext_lazy as _
from i18nfield.strings import LazyI18nString
from paypalrestsdk.exceptions import BadRequest, UnauthorizedAccess
from paypalrestsdk.openid_connect import Tokeninfo

from pretix.base.decimal import round_decimal
from pretix.base.models import Event, Order, OrderPayment, OrderRefund, Quota
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.services.mail import SendMailException
from pretix.base.settings import SettingsSandbox
from pretix.helpers.urls import build_absolute_uri as build_global_uri
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.plugins.paypal.models import ReferencedPayPalObject

logger = logging.getLogger('pretix.plugins.paypal')

SUPPORTED_CURRENCIES = ['AUD', 'BRL', 'CAD', 'CZK', 'DKK', 'EUR', 'HKD', 'HUF', 'INR', 'ILS', 'JPY', 'MYR', 'MXN',
                        'TWD', 'NZD', 'NOK', 'PHP', 'PLN', 'GBP', 'RUB', 'SGD', 'SEK', 'CHF', 'THB', 'USD']

LOCAL_ONLY_CURRENCIES = ['INR']


class Paypal(BasePaymentProvider):
    identifier = 'paypal'
    verbose_name = _('PayPal')
    payment_form_fields = OrderedDict([
    ])

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('payment', 'paypal', event)

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

    @property
    def settings_form_fields(self):
        if self.settings.connect_client_id and not self.settings.secret:
            # PayPal connect
            if self.settings.connect_user_id:
                fields = [
                    ('connect_user_id',
                     forms.CharField(
                         label=_('PayPal account'),
                         disabled=True
                     )),
                ]
            else:
                return {}
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

        extra_fields = [
            ('prefix',
             forms.CharField(
                 label=_('Reference prefix'),
                 help_text=_('Any value entered here will be added in front of the regular booking reference '
                             'containing the order number.'),
                 required=False,
             ))
        ]

        d = OrderedDict(
            fields + extra_fields + list(super().settings_form_fields.items())
        )

        d.move_to_end('prefix')
        d.move_to_end('_enabled', False)
        return d

    def get_connect_url(self, request):
        request.session['payment_paypal_oauth_event'] = request.event.pk

        self.init_api()
        return Tokeninfo.authorize_url({'scope': 'openid profile email'})

    def settings_content_render(self, request):
        settings_content = ""
        if self.settings.connect_client_id and not self.settings.secret:
            # Use PayPal connect
            if not self.settings.connect_user_id:
                settings_content = (
                    "<p>{}</p>"
                    "<a href='{}' class='btn btn-primary btn-lg'>{}</a>"
                ).format(
                    _('To accept payments via PayPal, you will need an account at PayPal. By clicking on the '
                      'following button, you can either create a new PayPal account connect pretix to an existing '
                      'one.'),
                    self.get_connect_url(request),
                    _('Connect with {icon} PayPal').format(icon='<i class="fa fa-paypal"></i>')
                )
            else:
                settings_content = (
                    "<button formaction='{}' class='btn btn-danger'>{}</button>"
                ).format(
                    reverse('plugins:paypal:oauth.disconnect', kwargs={
                        'organizer': self.event.organizer.slug,
                        'event': self.event.slug,
                    }),
                    _('Disconnect from PayPal')
                )
        else:
            settings_content = "<div class='alert alert-info'>%s<br /><code>%s</code></div>" % (
                _('Please configure a PayPal Webhook to the following endpoint in order to automatically cancel orders '
                  'when payments are refunded externally.'),
                build_global_uri('plugins:paypal:webhook')
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

    def is_allowed(self, request: HttpRequest, total: Decimal = None) -> bool:
        return super().is_allowed(request, total) and self.event.currency in SUPPORTED_CURRENCIES

    def init_api(self):
        if self.settings.connect_client_id and not self.settings.secret:
            paypalrestsdk.set_config(
                mode="sandbox" if "sandbox" in self.settings.connect_endpoint else 'live',
                client_id=self.settings.connect_client_id,
                client_secret=self.settings.connect_secret_key,
                openid_client_id=self.settings.connect_client_id,
                openid_client_secret=self.settings.connect_secret_key,
                openid_redirect_uri=urllib.parse.quote(build_global_uri('plugins:paypal:oauth.return')))
        else:
            paypalrestsdk.set_config(
                mode="sandbox" if "sandbox" in self.settings.get('endpoint') else 'live',
                client_id=self.settings.get('client_id'),
                client_secret=self.settings.get('secret'))

    def payment_is_valid_session(self, request):
        return (request.session.get('payment_paypal_id', '') != ''
                and request.session.get('payment_paypal_payer', '') != '')

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/paypal/checkout_payment_form.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings}
        return template.render(ctx)

    def checkout_prepare(self, request, cart):
        self.init_api()
        kwargs = {}
        if request.resolver_match and 'cart_namespace' in request.resolver_match.kwargs:
            kwargs['cart_namespace'] = request.resolver_match.kwargs['cart_namespace']

        try:
            if request.event.settings.payment_paypal_connect_user_id:
                try:
                    tokeninfo = Tokeninfo.create_with_refresh_token(request.event.settings.payment_paypal_connect_refresh_token)
                except BadRequest as ex:
                    ex = json.loads(ex.content)
                    messages.error(request, '{}: {} ({})'.format(
                        _('We had trouble communicating with PayPal'),
                        ex['error_description'],
                        ex['correlation_id'])
                    )
                    return

                # Even if the token has been refreshed, calling userinfo() can fail. In this case we just don't
                # get the userinfo again and use the payment_paypal_connect_user_id that we already have on file
                try:
                    userinfo = tokeninfo.userinfo()
                    request.event.settings.payment_paypal_connect_user_id = userinfo.email
                except UnauthorizedAccess:
                    pass

                payee = {
                    "email": request.event.settings.payment_paypal_connect_user_id,
                    # If PayPal ever offers a good way to get the MerchantID via the Identifity API,
                    # we should use it instead of the merchant's eMail-address
                    # "merchant_id": request.event.settings.payment_paypal_connect_user_id,
                }
            else:
                payee = {}

            payment = paypalrestsdk.Payment({
                'header': {'PayPal-Partner-Attribution-Id': 'ramiioSoftwareentwicklung_SP'},
                'intent': 'sale',
                'payer': {
                    "payment_method": "paypal",
                },
                "redirect_urls": {
                    "return_url": build_absolute_uri(request.event, 'plugins:paypal:return', kwargs=kwargs),
                    "cancel_url": build_absolute_uri(request.event, 'plugins:paypal:abort', kwargs=kwargs),
                },
                "transactions": [
                    {
                        "item_list": {
                            "items": [
                                {
                                    "name": ('{} '.format(self.settings.prefix) if self.settings.prefix else '') +
                                    __('Order for %s') % str(request.event),
                                    "quantity": 1,
                                    "price": self.format_price(cart['total']),
                                    "currency": request.event.currency
                                }
                            ]
                        },
                        "amount": {
                            "currency": request.event.currency,
                            "total": self.format_price(cart['total'])
                        },
                        "description": __('Event tickets for {event}').format(event=request.event.name),
                        "payee": payee
                    }
                ]
            })
            request.session['payment_paypal_payment'] = None
            return self._create_payment(request, payment)
        except paypalrestsdk.exceptions.ConnectionError as e:
            messages.error(request, _('We had trouble communicating with PayPal'))
            logger.exception('Error on creating payment: ' + str(e))

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

    def _create_payment(self, request, payment):
        if payment.create():
            if payment.state not in ('created', 'approved', 'pending'):
                messages.error(request, _('We had trouble communicating with PayPal'))
                logger.error('Invalid payment state: ' + str(payment))
                return
            request.session['payment_paypal_id'] = payment.id
            for link in payment.links:
                if link.method == "REDIRECT" and link.rel == "approval_url":
                    if request.session.get('iframe_session', False):
                        signer = signing.Signer(salt='safe-redirect')
                        return (
                            build_absolute_uri(request.event, 'plugins:paypal:redirect') + '?url=' +
                            urllib.parse.quote(signer.sign(link.href))
                        )
                    else:
                        return str(link.href)
        else:
            messages.error(request, _('We had trouble communicating with PayPal'))
            logger.error('Error on creating payment: ' + str(payment.error))

    def checkout_confirm_render(self, request) -> str:
        """
        Returns the HTML that should be displayed when the user selected this provider
        on the 'confirm order' page.
        """
        template = get_template('pretixplugins/paypal/checkout_payment_confirm.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings}
        return template.render(ctx)

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        if (request.session.get('payment_paypal_id', '') == '' or request.session.get('payment_paypal_payer', '') == ''):
            raise PaymentException(_('We were unable to process your payment. See below for details on how to '
                                     'proceed.'))

        self.init_api()
        pp_payment = paypalrestsdk.Payment.find(request.session.get('payment_paypal_id'))
        ReferencedPayPalObject.objects.get_or_create(order=payment.order, payment=payment, reference=pp_payment.id)
        if str(pp_payment.transactions[0].amount.total) != str(payment.amount) or pp_payment.transactions[0].amount.currency \
                != self.event.currency:
            logger.error('Value mismatch: Payment %s vs paypal trans %s' % (payment.id, str(pp_payment)))
            raise PaymentException(_('We were unable to process your payment. See below for details on how to '
                                     'proceed.'))

        return self._execute_payment(pp_payment, request, payment)

    def _execute_payment(self, payment, request, payment_obj):
        if payment.state == 'created':
            payment.replace([
                {
                    "op": "replace",
                    "path": "/transactions/0/item_list",
                    "value": {
                        "items": [
                            {
                                "name": ('{} '.format(self.settings.prefix) if self.settings.prefix else '') +
                                __('Order {slug}-{code}').format(
                                    slug=self.event.slug.upper(), code=payment_obj.order.code
                                ),
                                "quantity": 1,
                                "price": self.format_price(payment_obj.amount),
                                "currency": payment_obj.order.event.currency
                            }
                        ]
                    }
                },
                {
                    "op": "replace",
                    "path": "/transactions/0/description",
                    "value": ('{} '.format(self.settings.prefix) if self.settings.prefix else '') +
                    __('Order {order} for {event}').format(
                        event=request.event.name,
                        order=payment_obj.order.code
                    )
                }
            ])
            try:
                payment.execute({"payer_id": request.session.get('payment_paypal_payer')})
            except paypalrestsdk.exceptions.ConnectionError as e:
                messages.error(request, _('We had trouble communicating with PayPal'))
                logger.exception('Error on creating payment: ' + str(e))

        for trans in payment.transactions:
            for rr in trans.related_resources:
                if hasattr(rr, 'sale') and rr.sale:
                    if rr.sale.state == 'pending':
                        messages.warning(request, _('PayPal has not yet approved the payment. We will inform you as '
                                                    'soon as the payment completed.'))
                        payment_obj.info = json.dumps(payment.to_dict())
                        payment_obj.state = OrderPayment.PAYMENT_STATE_PENDING
                        payment_obj.save()
                        return

        payment_obj.refresh_from_db()
        if payment.state == 'pending':
            messages.warning(request, _('PayPal has not yet approved the payment. We will inform you as soon as the '
                                        'payment completed.'))
            payment_obj.info = json.dumps(payment.to_dict())
            payment_obj.state = OrderPayment.PAYMENT_STATE_PENDING
            payment_obj.save()
            return

        if payment.state != 'approved':
            payment_obj.fail(info=payment.to_dict())
            logger.error('Invalid state: %s' % str(payment))
            raise PaymentException(_('We were unable to process your payment. See below for details on how to '
                                     'proceed.'))

        if payment_obj.state == OrderPayment.PAYMENT_STATE_CONFIRMED:
            logger.warning('PayPal success event even though order is already marked as paid')
            return

        try:
            payment_obj.info = json.dumps(payment.to_dict())
            payment_obj.save(update_fields=['info'])
            payment_obj.confirm()
        except Quota.QuotaExceededException as e:
            raise PaymentException(str(e))

        except SendMailException:
            messages.warning(request, _('There was an error sending the confirmation mail.'))
        return None

    def payment_pending_render(self, request, payment) -> str:
        retry = True
        try:
            if payment.info and payment.info_data['state'] == 'pending':
                retry = False
        except KeyError:
            pass
        template = get_template('pretixplugins/paypal/pending.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings,
               'retry': retry, 'order': payment.order}
        return template.render(ctx)

    def matching_id(self, payment: OrderPayment):
        sale_id = None
        for trans in payment.info_data.get('transactions', []):
            for res in trans.get('related_resources', []):
                if 'sale' in res and 'id' in res['sale']:
                    sale_id = res['sale']['id']
        return sale_id or payment.info_data.get('id', None)

    def api_payment_details(self, payment: OrderPayment):
        sale_id = None
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

    def payment_control_render(self, request: HttpRequest, payment: OrderPayment):
        template = get_template('pretixplugins/paypal/control.html')
        sale_id = None
        for trans in payment.info_data.get('transactions', []):
            for res in trans.get('related_resources', []):
                if 'sale' in res and 'id' in res['sale']:
                    sale_id = res['sale']['id']
        ctx = {'request': request, 'event': self.event, 'settings': self.settings,
               'payment_info': payment.info_data, 'order': payment.order, 'sale_id': sale_id}
        return template.render(ctx)

    def payment_control_render_short(self, payment: OrderPayment) -> str:
        return payment.info_data.get('payer', {}).get('payer_info', {}).get('email', '')

    def payment_partial_refund_supported(self, payment: OrderPayment):
        # Paypal refunds are possible for 180 days after purchase:
        # https://www.paypal.com/lc/smarthelp/article/how-do-i-issue-a-refund-faq780#:~:text=Refund%20after%20180%20days%20of,PayPal%20balance%20of%20the%20recipient.
        return (now() - payment.payment_date).days <= 180

    def payment_refund_supported(self, payment: OrderPayment):
        self.payment_partial_refund_supported(payment)

    def execute_refund(self, refund: OrderRefund):
        self.init_api()

        try:
            sale = None
            for res in refund.payment.info_data['transactions'][0]['related_resources']:
                for k, v in res.items():
                    if k == 'sale':
                        sale = paypalrestsdk.Sale.find(v['id'])
                        break

            pp_refund = sale.refund({
                "amount": {
                    "total": self.format_price(refund.amount),
                    "currency": refund.order.event.currency
                }
            })
        except paypalrestsdk.exceptions.ConnectionError as e:
            refund.order.log_action('pretix.event.order.refund.failed', {
                'local_id': refund.local_id,
                'provider': refund.provider,
                'error': str(e)
            })
            raise PaymentException(_('Refunding the amount via PayPal failed: {}').format(str(e)))
        if not pp_refund.success():
            refund.order.log_action('pretix.event.order.refund.failed', {
                'local_id': refund.local_id,
                'provider': refund.provider,
                'error': str(pp_refund.error)
            })
            raise PaymentException(_('Refunding the amount via PayPal failed: {}').format(pp_refund.error))
        else:
            sale = paypalrestsdk.Payment.find(refund.payment.info_data['id'])
            refund.payment.info = json.dumps(sale.to_dict())
            refund.info = json.dumps(pp_refund.to_dict())
            refund.done()

    def payment_prepare(self, request, payment_obj):
        self.init_api()

        try:
            if request.event.settings.payment_paypal_connect_user_id:
                try:
                    tokeninfo = Tokeninfo.create_with_refresh_token(request.event.settings.payment_paypal_connect_refresh_token)
                except BadRequest as ex:
                    ex = json.loads(ex.content)
                    messages.error(request, '{}: {} ({})'.format(
                        _('We had trouble communicating with PayPal'),
                        ex['error_description'],
                        ex['correlation_id'])
                    )
                    return

                # Even if the token has been refreshed, calling userinfo() can fail. In this case we just don't
                # get the userinfo again and use the payment_paypal_connect_user_id that we already have on file
                try:
                    userinfo = tokeninfo.userinfo()
                    request.event.settings.payment_paypal_connect_user_id = userinfo.email
                except UnauthorizedAccess:
                    pass

                payee = {
                    "email": request.event.settings.payment_paypal_connect_user_id,
                    # If PayPal ever offers a good way to get the MerchantID via the Identifity API,
                    # we should use it instead of the merchant's eMail-address
                    # "merchant_id": request.event.settings.payment_paypal_connect_user_id,
                }
            else:
                payee = {}

            payment = paypalrestsdk.Payment({
                'header': {'PayPal-Partner-Attribution-Id': 'ramiioSoftwareentwicklung_SP'},
                'intent': 'sale',
                'payer': {
                    "payment_method": "paypal",
                },
                "redirect_urls": {
                    "return_url": build_absolute_uri(request.event, 'plugins:paypal:return'),
                    "cancel_url": build_absolute_uri(request.event, 'plugins:paypal:abort'),
                },
                "transactions": [
                    {
                        "item_list": {
                            "items": [
                                {
                                    "name": ('{} '.format(self.settings.prefix) if self.settings.prefix else '') +
                                    __('Order {slug}-{code}').format(
                                        slug=self.event.slug.upper(),
                                        code=payment_obj.order.code
                                    ),
                                    "quantity": 1,
                                    "price": self.format_price(payment_obj.amount),
                                    "currency": payment_obj.order.event.currency
                                }
                            ]
                        },
                        "amount": {
                            "currency": request.event.currency,
                            "total": self.format_price(payment_obj.amount)
                        },
                        "description": ('{} '.format(self.settings.prefix) if self.settings.prefix else '') +
                        __('Order {order} for {event}').format(
                            event=request.event.name,
                            order=payment_obj.order.code
                        ),
                        "payee": payee
                    }
                ]
            })
            request.session['payment_paypal_payment'] = payment_obj.pk
            return self._create_payment(request, payment)
        except paypalrestsdk.exceptions.ConnectionError as e:
            messages.error(request, _('We had trouble communicating with PayPal'))
            logger.exception('Error on creating payment: ' + str(e))

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
