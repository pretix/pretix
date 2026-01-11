import logging
import hashlib
import hmac
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from pretix.base.models import Order, OrderPayment
from pretix.multidomain.urlreverse import eventreverse
from pretix.base.payment import PaymentException

logger = logging.getLogger('pretix.plugins.onepay')

class ReturnView(View):
    def get(self, request, *args, **kwargs):
        # Parse parameters
        params = request.GET.dict()
        vpc_TxnResponseCode = params.get('vpc_TxnResponseCode')
        vpc_MerchTxnRef = params.get('vpc_MerchTxnRef')
        vpc_SecureHash = params.get('vpc_SecureHash')

        if not vpc_MerchTxnRef:
             messages.error(request, _('Invalid response from OnePay.'))
             return redirect(eventreverse(request.event, 'presale:event.checkout.start'))

        # Find payment
        try:
            # vpc_MerchTxnRef should be the payment full_id (e.g., A123-P-1)
            # We need to find the order and payment.
            # Assuming format ORDER-P-ID
            order_code, payment_local_id = vpc_MerchTxnRef.split('-P-')
            order = Order.objects.get(code=order_code, event=request.event)
            payment = order.payments.get(local_id=payment_local_id)
        except (ValueError, Order.DoesNotExist, OrderPayment.DoesNotExist):
            logger.error(f'OnePay return: Payment not found for ref {vpc_MerchTxnRef}')
            messages.error(request, _('Order not found.'))
            return redirect(eventreverse(request.event, 'presale:event.checkout.start'))

        # Verify Hash
        provider = payment.payment_provider
        if not provider:
             # Should not happen
             return redirect(eventreverse(request.event, 'presale:event.order', kwargs={
                'order': order.code,
                'secret': order.secret,
            }))

        hash_key = provider.settings.get('hash_key')

        # Remove vpc_SecureHash and vpc_SecureHashType from params to calculate hash
        hash_params = {k: v for k, v in params.items() if k not in ('vpc_SecureHash', 'vpc_SecureHashType') and len(v) > 0}

        query_params = []
        for key in sorted(hash_params.keys()):
            query_params.append(f"{key}={hash_params[key]}")
        querystring = "&".join(query_params)

        try:
            key = bytes.fromhex(hash_key)
        except ValueError:
            key = hash_key.encode('utf-8')

        signature = hmac.new(key, querystring.encode('utf-8'), hashlib.sha256).hexdigest().upper()

        if signature != vpc_SecureHash:
            logger.error(f'OnePay return: Hash mismatch. Calculated {signature}, received {vpc_SecureHash}')
            messages.error(request, _('Security check failed.'))
            payment.fail(info=params)
            return redirect(eventreverse(request.event, 'presale:event.order', kwargs={
                'order': order.code,
                'secret': order.secret,
            }))

        if vpc_TxnResponseCode == '0':
            # Success
            try:
                payment.confirm()
            except Exception as e:
                logger.error(f'OnePay return: Confirm failed {str(e)}')
                messages.error(request, _('Payment confirmation failed.'))

            return redirect(eventreverse(request.event, 'presale:event.order', kwargs={
                'order': order.code,
                'secret': order.secret,
            }))
        else:
            # Failed
            payment.fail(info=params)
            messages.error(request, _('Payment failed with response code: {}').format(vpc_TxnResponseCode))
            return redirect(eventreverse(request.event, 'presale:event.order', kwargs={
                'order': order.code,
                'secret': order.secret,
            }))
