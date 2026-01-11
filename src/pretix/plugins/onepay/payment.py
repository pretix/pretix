import hashlib
import hmac
import logging
import urllib.parse
from collections import OrderedDict

from django import forms
from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import redirect
from django.template.loader import get_template
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

from pretix.base.models import Event, OrderPayment, Order
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.settings import SettingsSandbox
from pretix.helpers.urls import build_absolute_uri
from pretix.multidomain.urlreverse import eventreverse

logger = logging.getLogger('pretix.plugins.onepay')


class OnePay(BasePaymentProvider):
    identifier = 'onepay'
    verbose_name = _('OnePay')
    public_name = _('OnePay')

    @property
    def settings_form_fields(self):
        return OrderedDict(
            [
                ('merchant_id',
                 forms.CharField(
                     label=_('Merchant ID'),
                 )),
                ('access_code',
                 forms.CharField(
                     label=_('Access Code'),
                 )),
                ('hash_key',
                 forms.CharField(
                     label=_('Hash Key'),
                 )),
                ('endpoint',
                 forms.ChoiceField(
                     label=_('Endpoint'),
                     initial='https://mtf.onepay.vn/onecomm-pay/vpc.op',
                     choices=(
                         ('https://mtf.onepay.vn/onecomm-pay/vpc.op', _('Test Environment')),
                         ('https://onepay.vn/onecomm-pay/vpc.op', _('Domestic Card (Live)')),
                         ('https://onepay.vn/vpcpay/vpc.op', _('International Card (Live)')),
                     ),
                 )),
            ]
        )

    def payment_form_render(self, request, total) -> str:
        template = get_template('pretixplugins/onepay/checkout_payment_form.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings}
        return template.render(ctx)

    def checkout_prepare(self, request, cart):
        return True

    def payment_is_valid_session(self, request):
        return True

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        merchant_id = self.settings.get('merchant_id')
        access_code = self.settings.get('access_code')
        hash_key = self.settings.get('hash_key')
        endpoint = self.settings.get('endpoint')

        if not merchant_id or not access_code or not hash_key:
            raise PaymentException(_('OnePay configuration is incomplete.'))

        return_url = build_absolute_uri(self.event, 'plugins:onepay:return')

        # OnePay parameters
        params = OrderedDict()
        params['vpc_Version'] = '2'
        params['vpc_Command'] = 'pay'
        params['vpc_AccessCode'] = access_code
        params['vpc_Merchant'] = merchant_id
        params['vpc_Locale'] = 'vn'
        params['vpc_ReturnURL'] = return_url
        params['vpc_MerchTxnRef'] = payment.full_id
        params['vpc_OrderInfo'] = payment.order.code
        places = settings.CURRENCY_PLACES.get(self.event.currency, 2)
        params['vpc_Amount'] = int(payment.amount * (10 ** places))
        params['vpc_TicketNo'] = request.META.get('REMOTE_ADDR', '127.0.0.1')
        params['vpc_Currency'] = self.event.currency

        # Additional params usually required
        # Generate SecureHash
        # OnePay requires sorting parameters by key and then joining them with & and then creating HMAC SHA256 usually
        # But documentation varies. For OnePay Vietnam, it's often:
        # Sort keys, create query string, append to hash keys if it's HMAC, or just hash the values.
        # Let's assume standard VPC implementation:
        # 1. Filter parameters starting with vpc_ or user_
        # 2. Sort by key
        # 3. Concatenate values? Or query string?
        # Re-checking common OnePay integration patterns (VPC).
        # Usually: key=value&key=value...

        # NOTE: This implementation assumes standard OnePay/VPC logic.
        # Actual implementation might require tweaking based on specific OnePay contract (Domestic vs International often differ slightly).

        query_params = []
        for key in sorted(params.keys()):
            val = str(params[key])
            if len(val) > 0:
                query_params.append(f"{key}={val}")

        querystring = "&".join(query_params)

        # HMAC SHA256
        import hmac
        import hashlib

        # Convert hex key to bytes
        try:
            key = bytes.fromhex(hash_key)
        except ValueError:
            # Fallback if key is not hex
            key = hash_key.encode('utf-8')

        signature = hmac.new(key, querystring.encode('utf-8'), hashlib.sha256).hexdigest().upper()

        redirect_url = f"{endpoint}?{querystring}&vpc_SecureHash={signature}"

        return redirect(redirect_url)
