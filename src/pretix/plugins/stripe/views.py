import hashlib
import json
import logging

import stripe
from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from pretix.base.models import Order, Quota, RequiredAction
from pretix.base.payment import PaymentException
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.orders import mark_order_paid, mark_order_refunded
from pretix.control.permissions import event_permission_required
from pretix.multidomain.urlreverse import eventreverse
from pretix.plugins.stripe.models import ReferencedStripeObject
from pretix.plugins.stripe.payment import StripeCC

logger = logging.getLogger('pretix.plugins.stripe')


@csrf_exempt
@require_POST
def webhook(request, *args, **kwargs):
    event_json = json.loads(request.body.decode('utf-8'))

    # We do not check for the event type as we are not interested in the event it self,
    # we just use it as a trigger to look the charge up to be absolutely sure.
    # Another reason for this is that stripe events are not authenticated, so they could
    # come from anywhere.

    if event_json['data']['object']['object'] == "charge":
        func = charge_webhook
        objid = event_json['data']['object']['id']
    elif event_json['data']['object']['object'] == "dispute":
        func = charge_webhook
        objid = event_json['data']['object']['charge']
    elif event_json['data']['object']['object'] == "source":
        func = source_webhook
        objid = event_json['data']['object']['id']
    else:
        return HttpResponse("Not interested in this data type", status=200)

    try:
        rso = ReferencedStripeObject.objects.select_related('order', 'order__event').get(reference=objid)
        return func(rso.order.event, event_json, objid)
    except ReferencedStripeObject.DoesNotExist:
        if hasattr(request, 'event'):
            return func(request.event, event_json, objid)
        else:
            return HttpResponse("Unable to detect event", status=200)


def charge_webhook(event, event_json, charge_id):
    prov = StripeCC(event)
    prov._init_api()
    try:
        charge = stripe.Charge.retrieve(charge_id)
    except stripe.error.StripeError:
        logger.exception('Stripe error on webhook. Event data: %s' % str(event_json))
        return HttpResponse('Charge not found', status=500)

    metadata = charge['metadata']
    if 'event' not in metadata:
        return HttpResponse('Event not given in charge metadata', status=200)

    if int(metadata['event']) != event.pk:
        return HttpResponse('Not interested in this event', status=200)

    try:
        order = event.orders.get(id=metadata['order'], payment_provider__startswith='stripe')
    except Order.DoesNotExist:
        return HttpResponse('Order not found', status=200)

    if order.payment_provider != prov.identifier:
        prov = event.get_payment_providers()[order.payment_provider]
        prov._init_api()

    order.log_action('pretix.plugins.stripe.event', data=event_json)

    is_refund = charge['refunds']['total_count'] or charge['dispute']
    if order.status == Order.STATUS_PAID and is_refund:
        RequiredAction.objects.create(
            event=event, action_type='pretix.plugins.stripe.refund', data=json.dumps({
                'order': order.code,
                'charge': charge_id
            })
        )
    elif order.status in (Order.STATUS_PENDING, Order.STATUS_EXPIRED) and charge['status'] == 'succeeded' and not is_refund:
        try:
            mark_order_paid(order, user=None)
        except LockTimeoutException:
            return HttpResponse("Lock timeout, please try again.", status=503)
        except Quota.QuotaExceededException:
            if not RequiredAction.objects.filter(event=event, action_type='pretix.plugins.stripe.overpaid',
                                                 data__icontains=order.code).exists():
                RequiredAction.objects.create(
                    event=event,
                    action_type='pretix.plugins.stripe.overpaid',
                    data=json.dumps({
                        'order': order.code,
                        'charge': charge.id
                    })
                )

    return HttpResponse(status=200)


def source_webhook(event, event_json, source_id):
    prov = StripeCC(event)
    prov._init_api()
    try:
        src = stripe.Source.retrieve(source_id)
    except stripe.error.StripeError:
        logger.exception('Stripe error on webhook. Event data: %s' % str(event_json))
        return HttpResponse('Charge not found', status=500)

    metadata = src['metadata']
    if 'event' not in metadata:
        return HttpResponse('Event not given in charge metadata', status=200)

    if int(metadata['event']) != event.pk:
        return HttpResponse('Not interested in this event', status=200)

    with transaction.atomic():
        try:
            order = event.orders.get(id=metadata['order'], payment_provider__startswith='stripe')
        except Order.DoesNotExist:
            return HttpResponse('Order not found', status=200)

        if order.payment_provider != prov.identifier:
            prov = event.get_payment_providers()[order.payment_provider]
            prov._init_api()

        order.log_action('pretix.plugins.stripe.event', data=event_json)
        go = (event_json['type'] == 'source.chargeable' and order.status == Order.STATUS_PENDING and
              src.status == 'chargeable')
        if go:
            try:
                prov._charge_source(None, source_id, order)
            except PaymentException:
                logger.exception('Webhook error')

    return HttpResponse(status=200)


@event_permission_required('can_view_orders')
@require_POST
def refund(request, **kwargs):
    with transaction.atomic():
        action = get_object_or_404(RequiredAction, event=request.event, pk=kwargs.get('id'),
                                   action_type='pretix.plugins.stripe.refund', done=False)
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


class StripeOrderView:
    def dispatch(self, request, *args, **kwargs):
        try:
            self.order = request.event.orders.get(code=kwargs['order'])
            if hashlib.sha1(self.order.secret.lower().encode()).hexdigest() != kwargs['hash'].lower():
                raise Http404('')
        except Order.DoesNotExist:
            # Do a hash comparison as well to harden timing attacks
            if 'abcdefghijklmnopq'.lower() == hashlib.sha1('abcdefghijklmnopq'.encode()).hexdigest():
                raise Http404('')
            else:
                raise Http404('')
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def pprov(self):
        return self.request.event.get_payment_providers()[self.order.payment_provider]


@method_decorator(xframe_options_exempt, 'dispatch')
class ReturnView(StripeOrderView, View):
    def get(self, request, *args, **kwargs):
        prov = self.pprov
        prov._init_api()
        src = stripe.Source.retrieve(request.GET.get('source'))
        if src.client_secret != request.GET.get('client_secret'):
            messages.error(self.request, _('Sorry, there was an error in the payment process. Please check the link '
                                           'in your emails to continue.'))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        with transaction.atomic():
            self.order.refresh_from_db()
            if self.order.status == Order.STATUS_PAID:
                if 'payment_stripe_token' in request.session:
                    del request.session['payment_stripe_token']
                return self._redirect_to_order()

            if src.status == 'chargeable':
                try:
                    prov._charge_source(request, src.id, self.order)
                except PaymentException as e:
                    messages.error(request, str(e))
                    return self._redirect_to_order()
                finally:
                    if 'payment_stripe_token' in request.session:
                        del request.session['payment_stripe_token']
            else:
                messages.error(self.request, _('We had trouble authorizing your card payment. Please try again and '
                                               'get in touch with us if this problem persists.'))
        return self._redirect_to_order()

    def _redirect_to_order(self):
        if self.request.session.get('payment_stripe_order_secret') != self.order.secret:
            messages.error(self.request, _('Sorry, there was an error in the payment process. Please check the link '
                                           'in your emails to continue.'))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        return redirect(eventreverse(self.request.event, 'presale:event.order', kwargs={
            'order': self.order.code,
            'secret': self.order.secret
        }) + ('?paid=yes' if self.order.status == Order.STATUS_PAID else ''))
