import json
import logging

import paypalrestsdk
from django.contrib import messages
from django.core import signing
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from pretix.base.models import Order, Quota, RequiredAction
from pretix.base.payment import PaymentException
from pretix.base.services.orders import mark_order_paid, mark_order_refunded
from pretix.control.permissions import event_permission_required
from pretix.multidomain.urlreverse import eventreverse
from pretix.plugins.paypal.payment import Paypal
from pretix.plugins.stripe.models import ReferencedStripeObject

logger = logging.getLogger('pretix.plugins.paypal')


@xframe_options_exempt
def redirect_view(request, *args, **kwargs):
    signer = signing.Signer(salt='safe-redirect')
    try:
        url = signer.unsign(request.GET.get('url', ''))
    except signing.BadSignature:
        return HttpResponseBadRequest('Invalid parameter')

    r = render(request, 'pretixplugins/paypal/redirect.html', {
        'url': url,
    })
    r._csp_ignore = True
    return r


def success(request, *args, **kwargs):
    pid = request.GET.get('paymentId')
    token = request.GET.get('token')
    payer = request.GET.get('PayerID')
    request.session['payment_paypal_token'] = token
    request.session['payment_paypal_payer'] = payer

    urlkwargs = {}
    if 'cart_namespace' in kwargs:
        urlkwargs['cart_namespace'] = kwargs['cart_namespace']

    if request.session.get('payment_paypal_order'):
        order = Order.objects.get(pk=request.session.get('payment_paypal_order'))
    else:
        order = None

    if pid == request.session.get('payment_paypal_id', None):
        if order:
            prov = Paypal(request.event)
            try:
                resp = prov.payment_perform(request, order)
            except PaymentException as e:
                messages.error(request, str(e))
                urlkwargs['step'] = 'payment'
                return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs=urlkwargs))
            if resp:
                return resp
    else:
        messages.error(request, _('Invalid response from PayPal received.'))
        logger.error('Session did not contain payment_paypal_id')
        urlkwargs['step'] = 'payment'
        return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs=urlkwargs))

    if order:
        return redirect(eventreverse(request.event, 'presale:event.order', kwargs={
            'order': order.code,
            'secret': order.secret
        }) + ('?paid=yes' if order.status == Order.STATUS_PAID else ''))
    else:
        urlkwargs['step'] = 'confirm'
        return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs=urlkwargs))


def abort(request, *args, **kwargs):
    messages.error(request, _('It looks like you canceled the PayPal payment'))

    if request.session.get('payment_paypal_order'):
        order = Order.objects.get(pk=request.session.get('payment_paypal_order'))
    else:
        order = None

    if order:
        return redirect(eventreverse(request.event, 'presale:event.order', kwargs={
            'order': order.code,
            'secret': order.secret
        }) + ('?paid=yes' if order.status == Order.STATUS_PAID else ''))
    else:
        return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs={'step': 'payment'}))


@csrf_exempt
@require_POST
def webhook(request, *args, **kwargs):
    event_body = request.body.decode('utf-8').strip()
    event_json = json.loads(event_body)

    # We do not check the signature, we just use it as a trigger to look the charge up.
    if event_json['resource_type'] not in ('sale', 'refund'):
        return HttpResponse("Not interested in this resource type", status=200)

    if event_json['resource_type'] == 'sale':
        saleid = event_json['resource']['id']
    else:
        saleid = event_json['resource']['sale_id']

    try:
        refs = [saleid]
        if event_json['resource'].get('parent_payment'):
            refs.append(event_json['resource'].get('parent_payment'))

        rso = ReferencedStripeObject.objects.select_related('order', 'order__event').get(
            reference__in=refs
        )
        event = rso.order.event
    except ReferencedStripeObject.DoesNotExist:
        if hasattr(request, 'event'):
            event = request.event
        else:
            return HttpResponse("Unable to detect event", status=200)

    prov = Paypal(event)
    prov.init_api()

    try:
        sale = paypalrestsdk.Sale.find(saleid)
    except:
        logger.exception('PayPal error on webhook. Event data: %s' % str(event_json))
        return HttpResponse('Sale not found', status=500)

    orders = Order.objects.filter(event=event, payment_provider='paypal',
                                  payment_info__icontains=sale['id'])
    order = None
    for o in orders:
        payment_info = json.loads(o.payment_info)
        for res in payment_info['transactions'][0]['related_resources']:
            for k, v in res.items():
                if k == 'sale' and v['id'] == sale['id']:
                    order = o
                    break

    if not order:
        return HttpResponse('Order not found', status=200)

    order.log_action('pretix.plugins.paypal.event', data=event_json)

    if order.status == Order.STATUS_PAID and sale['state'] in ('partially_refunded', 'refunded'):
        RequiredAction.objects.create(
            event=event, action_type='pretix.plugins.paypal.refund', data=json.dumps({
                'order': order.code,
                'sale': sale['id']
            })
        )
    elif order.status in (Order.STATUS_PENDING, Order.STATUS_EXPIRED) and sale['state'] == 'completed':
        try:
            mark_order_paid(order, user=None)
        except Quota.QuotaExceededException:
            if not RequiredAction.objects.filter(event=event, action_type='pretix.plugins.paypal.overpaid',
                                                 data__icontains=order.code).exists():
                RequiredAction.objects.create(
                    event=event, action_type='pretix.plugins.paypal.overpaid', data=json.dumps({
                        'order': order.code,
                        'payment': sale['parent_payment']
                    })
                )

    return HttpResponse(status=200)


@event_permission_required('can_view_orders')
@require_POST
def refund(request, **kwargs):
    with transaction.atomic():
        action = get_object_or_404(RequiredAction, event=request.event, pk=kwargs.get('id'),
                                   action_type='pretix.plugins.paypal.refund', done=False)
        data = json.loads(action.data)
        action.done = True
        action.user = request.user
        action.save()
        order = get_object_or_404(Order, event=request.event, code=data['order'])
        if order.status != Order.STATUS_PAID:
            messages.error(request, _('The order cannot be marked as refunded as it is not marked as paid!'))
        else:
            mark_order_refunded(order, user=request.user)
            messages.success(
                request, _('The order has been marked as refunded and the issue has been marked as resolved!')
            )

    return redirect(reverse('control:event.order', kwargs={
        'organizer': request.event.organizer.slug,
        'event': request.event.slug,
        'code': data['order']
    }))
