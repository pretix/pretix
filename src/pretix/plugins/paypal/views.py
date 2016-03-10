import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event, Order
from pretix.multidomain.urlreverse import eventreverse
from pretix.plugins.paypal.payment import Paypal

logger = logging.getLogger('pretix.plugins.paypal')


def success(request, organizer=None, event=None):
    pid = request.GET.get('paymentId')
    token = request.GET.get('token')
    payer = request.GET.get('PayerID')
    if pid == request.session.get('payment_paypal_id', None):
        request.session['payment_paypal_token'] = token
        request.session['payment_paypal_payer'] = payer
        try:
            event = Event.objects.get(id=request.session['payment_paypal_event'])
            if request.session.get('payment_paypal_order'):
                prov = Paypal(event)
                order = Order.objects.get(pk=request.session.get('payment_paypal_order'))
                resp = prov.payment_perform(request, order)
                return redirect(resp or eventreverse(event, 'presale:event.order', kwargs={
                    'order': order.code,
                    'secret': order.secret
                }) + '?paid=yes')
            return redirect(eventreverse(event, 'presale:event.checkout', kwargs={'step': 'confirm'}))
        except Event.DoesNotExist:
            pass  # TODO: Handle this
    else:
        pass  # TODO: Handle this


def abort(request, organizer=None, event=None):
    messages.error(request, _('It looks like you cancelled the PayPal payment'))
    try:
        event = Event.objects.get(id=request.session['payment_paypal_event'])
        return redirect(eventreverse(event, 'presale:event.checkout', kwargs={'step': 'payment'}))
    except Event.DoesNotExist:
        pass  # TODO: Handle this
