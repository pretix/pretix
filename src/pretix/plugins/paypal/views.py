import json
import logging
from decimal import Decimal

import paypalrestsdk
import paypalrestsdk.exceptions
from django.contrib import messages
from django.core import signing
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_scopes import scopes_disabled
from paypalrestsdk.openid_connect import Tokeninfo

from pretix.base.models import Event, Order, OrderPayment, OrderRefund, Quota
from pretix.base.payment import PaymentException
from pretix.control.permissions import event_permission_required
from pretix.multidomain.urlreverse import eventreverse
from pretix.plugins.paypal.models import ReferencedPayPalObject
from pretix.plugins.paypal.payment import Paypal

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


@scopes_disabled()
def oauth_return(request, *args, **kwargs):
    if 'payment_paypal_oauth_event' not in request.session:
        messages.error(request, _('An error occurred during connecting with PayPal, please try again.'))
        return redirect(reverse('control:index'))

    event = get_object_or_404(Event, pk=request.session['payment_paypal_oauth_event'])

    prov = Paypal(event)
    prov.init_api()

    try:
        tokeninfo = Tokeninfo.create(request.GET.get('code'))
        userinfo = Tokeninfo.create_with_refresh_token(tokeninfo['refresh_token']).userinfo()
    except paypalrestsdk.exceptions.ConnectionError:
        logger.exception('Failed to obtain OAuth token')
        messages.error(request, _('An error occurred during connecting with PayPal, please try again.'))
    else:
        messages.success(request,
                         _('Your PayPal account is now connected to pretix. You can change the settings in '
                           'detail below.'))

        event.settings.payment_paypal_connect_refresh_token = tokeninfo['refresh_token']
        event.settings.payment_paypal_connect_user_id = userinfo.email

    return redirect(reverse('control:event.settings.payment.provider', kwargs={
        'organizer': event.organizer.slug,
        'event': event.slug,
        'provider': 'paypal'
    }))


def success(request, *args, **kwargs):
    pid = request.GET.get('paymentId')
    token = request.GET.get('token')
    payer = request.GET.get('PayerID')
    request.session['payment_paypal_token'] = token
    request.session['payment_paypal_payer'] = payer

    urlkwargs = {}
    if 'cart_namespace' in kwargs:
        urlkwargs['cart_namespace'] = kwargs['cart_namespace']

    if request.session.get('payment_paypal_payment'):
        payment = OrderPayment.objects.get(pk=request.session.get('payment_paypal_payment'))
    else:
        payment = None

    if pid == request.session.get('payment_paypal_id', None):
        if payment:
            prov = Paypal(request.event)
            try:
                resp = prov.execute_payment(request, payment)
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

    if payment:
        return redirect(eventreverse(request.event, 'presale:event.order', kwargs={
            'order': payment.order.code,
            'secret': payment.order.secret
        }) + ('?paid=yes' if payment.order.status == Order.STATUS_PAID else ''))
    else:
        urlkwargs['step'] = 'confirm'
        return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs=urlkwargs))


def abort(request, *args, **kwargs):
    messages.error(request, _('It looks like you canceled the PayPal payment'))

    if request.session.get('payment_paypal_payment'):
        payment = OrderPayment.objects.get(pk=request.session.get('payment_paypal_payment'))
    else:
        payment = None

    if payment:
        return redirect(eventreverse(request.event, 'presale:event.order', kwargs={
            'order': payment.order.code,
            'secret': payment.order.secret
        }) + ('?paid=yes' if payment.order.status == Order.STATUS_PAID else ''))
    else:
        return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs={'step': 'payment'}))


@csrf_exempt
@require_POST
@scopes_disabled()
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

        rso = ReferencedPayPalObject.objects.select_related('order', 'order__event').get(
            reference__in=refs
        )
        event = rso.order.event
    except ReferencedPayPalObject.DoesNotExist:
        rso = None
        if hasattr(request, 'event'):
            event = request.event
        else:
            return HttpResponse("Unable to detect event", status=200)

    prov = Paypal(event)
    prov.init_api()

    try:
        sale = paypalrestsdk.Sale.find(saleid)
    except paypalrestsdk.exceptions.ConnectionError:
        logger.exception('PayPal error on webhook. Event data: %s' % str(event_json))
        return HttpResponse('Sale not found', status=500)

    if rso and rso.payment:
        payment = rso.payment
    else:
        payments = OrderPayment.objects.filter(order__event=event, provider='paypal',
                                               info__icontains=sale['id'])
        payment = None
        for p in payments:
            payment_info = p.info_data
            for res in payment_info['transactions'][0]['related_resources']:
                for k, v in res.items():
                    if k == 'sale' and v['id'] == sale['id']:
                        payment = p
                        break

    if not payment:
        return HttpResponse('Payment not found', status=200)

    payment.order.log_action('pretix.plugins.paypal.event', data=event_json)

    if payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED and sale['state'] in ('partially_refunded', 'refunded'):
        if event_json['resource_type'] == 'refund':
            try:
                refund = paypalrestsdk.Refund.find(event_json['resource']['id'])
            except paypalrestsdk.exceptions.ConnectionError:
                logger.exception('PayPal error on webhook. Event data: %s' % str(event_json))
                return HttpResponse('Refund not found', status=500)

            known_refunds = {r.info_data.get('id'): r for r in payment.refunds.all()}
            if refund['id'] not in known_refunds:
                payment.create_external_refund(
                    amount=abs(Decimal(refund['amount']['total'])),
                    info=json.dumps(refund.to_dict() if not isinstance(refund, dict) else refund)
                )
            elif known_refunds.get(refund['id']).state in (
                    OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_TRANSIT) and refund['state'] == 'completed':
                known_refunds.get(refund['id']).done()

            if 'total_refunded_amount' in refund:
                known_sum = payment.refunds.filter(
                    state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT,
                               OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_SOURCE_EXTERNAL)
                ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
                total_refunded_amount = Decimal(refund['total_refunded_amount']['value'])
                if known_sum < total_refunded_amount:
                    payment.create_external_refund(
                        amount=total_refunded_amount - known_sum
                    )
        elif sale['state'] == 'refunded':
            known_sum = payment.refunds.filter(
                state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT,
                           OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_SOURCE_EXTERNAL)
            ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

            if known_sum < payment.amount:
                payment.create_external_refund(
                    amount=payment.amount - known_sum
                )
    elif payment.state in (OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED,
                           OrderPayment.PAYMENT_STATE_CANCELED, OrderPayment.PAYMENT_STATE_FAILED) and sale['state'] == 'completed':
        try:
            payment.confirm()
        except Quota.QuotaExceededException:
            pass

    return HttpResponse(status=200)


@event_permission_required('can_change_event_settings')
@require_POST
def oauth_disconnect(request, **kwargs):
    del request.event.settings.payment_paypal_connect_refresh_token
    del request.event.settings.payment_paypal_connect_user_id
    request.event.settings.payment_paypal__enabled = False
    messages.success(request, _('Your PayPal account has been disconnected.'))

    return redirect(reverse('control:event.settings.payment.provider', kwargs={
        'organizer': request.event.organizer.slug,
        'event': request.event.slug,
        'provider': 'paypal'
    }))
