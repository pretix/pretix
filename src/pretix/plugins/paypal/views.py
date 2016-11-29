import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Order
from pretix.multidomain.urlreverse import eventreverse
from pretix.plugins.paypal.payment import Paypal
from pretix.presale.utils import event_view

logger = logging.getLogger('pretix.plugins.paypal')


@event_view(require_live=False)
def success(request, *args, **kwargs):
    pid = request.GET.get('paymentId')
    token = request.GET.get('token')
    payer = request.GET.get('PayerID')
    request.session['payment_paypal_token'] = token
    request.session['payment_paypal_payer'] = payer

    if request.session.get('payment_paypal_order'):
        order = Order.objects.get(pk=request.session.get('payment_paypal_order'))
    else:
        order = None

    if pid == request.session.get('payment_paypal_id', None):
        if order:
            prov = Paypal(request.event)
            resp = prov.payment_perform(request, order)
            if resp:
                return resp
    else:
        messages.error(request, _('Invalid response from PayPal received.'))
        logger.error('Session did not contain payment_paypal_id')
        return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs={'step': 'payment'}))

    if order:
        return redirect(eventreverse(request.event, 'presale:event.order', kwargs={
            'order': order.code,
            'secret': order.secret
        }) + ('?paid=yes' if order.status == Order.STATUS_PAID else ''))
    else:
        return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs={'step': 'confirm'}))


@event_view(require_live=False)
def abort(request, *args, **kwargs):
    messages.error(request, _('It looks like you canceled the PayPal payment'))
    return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs={'step': 'payment'}))
