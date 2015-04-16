import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
import paypalrestsdk
from pretix.base.models import Event, Order
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ugettext as __
from pretix.base.settings import SettingsSandbox
from pretix.plugins.paypal.payment import Paypal


logger = logging.getLogger('pretix.plugins.paypal')


@login_required
def success(request):
    pid = request.GET.get('paymentId')
    token = request.GET.get('token')
    payer = request.GET.get('PayerID')
    if pid == request.session['payment_paypal_id']:
        request.session['payment_paypal_token'] = token
        request.session['payment_paypal_payer'] = payer
        try:
            event = Event.objects.current.get(identity=request.session['payment_paypal_event'])
            return redirect(reverse('presale:event.checkout.confirm', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug,
            }))
        except Event.DoesNotExist:
            pass  # TODO: Handle this
    else:
        pass  # TODO: Handle this


@login_required
def abort(request):
    messages.error(request, _('It looks like you cancelled the PayPal payment'))
    try:
        event = Event.objects.current.get(identity=request.session['payment_paypal_event'])
        return redirect(reverse('presale:event.checkout.payment', kwargs={
            'event': event.slug,
            'organizer': event.organizer.slug,
        }))
    except Event.DoesNotExist:
        pass  # TODO: Handle this


@login_required
def retry(request, order):
    try:
        order = Order.objects.current.get(
            user=request.user,
            code=order,
        )
    except Order.DoesNotExist:
        return  # TODO: Handle this

    provider = Paypal(order.event)
    provider.init_api()

    if 'token' in request.GET:
        if 'PayerID' in request.GET:
            payment = paypalrestsdk.Payment.find(request.session.get('payment_paypal_id'))
            provider._execute_payment(payment, request, order)
        else:
            messages.error(request, _('It looks like you cancelled the PayPal payment'))
    else:
        payment = paypalrestsdk.Payment({
            'intent': 'sale',
            'payer': {
                "payment_method": "paypal",
            },
            "redirect_urls": {
                "return_url": request.build_absolute_uri(reverse('plugins:paypal:retry', kwargs={
                    'order': order.code
                })),
                "cancel_url": request.build_absolute_uri(reverse('plugins:paypal:retry', kwargs={
                    'order': order.code
                })),
            },
            "transactions": [
                {
                    "item_list": {
                        "items": [
                            {
                                "name": 'Order %s' % order.code,
                                "quantity": 1,
                                "price": str(order.total),
                                "currency": order.event.currency
                            }
                        ]
                    },
                    "amount": {
                        "currency": order.event.currency,
                        "total": str(order.total)
                    },
                    "description": __('Event tickets for %s') % order.event.name
                }
            ]
        })
        resp = provider._create_payment(request, payment)
        if resp:
            return redirect(resp)

    return redirect(reverse('presale:event.order', kwargs={
        'event': order.event.slug,
        'organizer': order.event.organizer.slug,
        'order': order.code,
    }))
