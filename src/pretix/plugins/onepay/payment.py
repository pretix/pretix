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
    def test_mode_message(self):
        if 'mtf.onepay.vn' in self.settings.get('endpoint', ''):
            return _('The OnePay plugin is operating in test mode. No money will actually be transferred.')
        return None

    @property
    def settings_form_fields(self):
        return OrderedDict(
            [
                ('merchant_id',
                 forms.CharField(
                     label=_('Merchant ID'),
                     help_text=_('Your OnePay Merchant ID.'),
                 )),
                ('access_code',
                 forms.CharField(
                     label=_('Access Code'),
                     help_text=_('Your OnePay Access Code.'),
                 )),
                ('hash_key',
                 forms.CharField(
                     label=_('Hash Key'),
                     help_text=_('Your OnePay Secure Hash Key (Hex or String).'),
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

        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        params['vpc_TicketNo'] = ip

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

        # Proper URL encoding is crucial
        # Note: OnePay hashing usually requires the RAW string (key=value&key=value) *before* URL encoding,
        # OR it requires hashing the values as they will be sent.
        # Standard VPC: Hash the string `key=value&key=value` (values not URL encoded), then URL encode the whole thing for the redirect.
        # However, `vpc_ReturnURL` often contains special chars.

        # Let's clarify OnePay/VPC standard:
        # 1. Create string for hashing: key=value&key=value (sorted by key). Values are NOT URL encoded yet?
        #    Actually, most VPC docs say values SHOULD be URL encoded *if* they contain special chars?
        #    Let's check `urllib.parse.urlencode`. It encodes by default.
        #    If OnePay expects raw values in hash, we must be careful.
        #    Common practice: Build dict, `urlencode` it to get query string, use that query string to sign?
        #    NO. Usually: keys are sorted.

        # Safe approach for Python and OnePay:
        # 1. Sort items.
        # 2. Build string `key=value&key=value` WITHOUT encoding for HASHING (if OnePay specifies so).
        #    BUT standard VPC often hashes the *URL-encoded* string?
        #    Let's assume the safest path: `urllib.parse.urlencode` handles spaces and special chars.
        #    Most modern gateways hash the query string as it appears in the URL.

        sorted_params = sorted(params.items())
        # Use urlencode to create the query string safely (handles ' ', '/', etc.)
        querystring = urllib.parse.urlencode(sorted_params)

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

        # The final URL needs the signature appended
        redirect_url = f"{endpoint}?{querystring}&vpc_SecureHash={signature}"

        return redirect(redirect_url)
