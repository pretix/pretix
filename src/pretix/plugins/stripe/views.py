import json
import logging

import stripe
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from pretix.base.models import Order, Quota, RequiredAction
from pretix.base.services.orders import mark_order_paid, mark_order_refunded
from pretix.control.permissions import event_permission_required
from pretix.plugins.stripe.payment import Stripe
from pretix.presale.utils import event_view

logger = logging.getLogger('pretix.plugins.stripe')


@csrf_exempt
@require_POST
@event_view(require_live=False)
def webhook(request, *args, **kwargs):
    event_json = json.loads(request.body.decode('utf-8'))

    # We do not check for the event type as we are not interested in the event it self,
    # we just use it as a trigger to look the charge up to be absolutely sure.
    # Another reason for this is that stripe events are not authenticated, so they could
    # come from anywhere.

    if event_json['data']['object']['object'] == "charge":
        charge_id = event_json['data']['object']['id']
    elif event_json['data']['object']['object'] == "dispute":
        charge_id = event_json['data']['object']['charge']
    else:
        return HttpResponse("Not interested in this data type", status=200)

    prov = Stripe(request.event)
    prov._init_api()
    try:
        charge = stripe.Charge.retrieve(charge_id)
    except stripe.error.StripeError:
        logger.exception('Stripe error on webhook. Event data: %s' % str(event_json))
        return HttpResponse('Charge not found', status=500)

    metadata = charge['metadata']
    if 'event' not in metadata:
        return HttpResponse('Event not given in charge metadata', status=200)

    if int(metadata['event']) != request.event.pk:
        return HttpResponse('Not interested in this event', status=200)

    try:
        order = request.event.orders.get(id=metadata['order'], payment_provider='stripe')
    except Order.DoesNotExist:
        return HttpResponse('Order not found', status=200)

    order.log_action('pretix.plugins.stripe.event', data=event_json)

    is_refund = charge['refunds']['total_count'] or charge['dispute']
    if order.status == Order.STATUS_PAID and is_refund:
        RequiredAction.objects.create(
            event=request.event, action_type='pretix.plugins.stripe.refund', data=json.dumps({
                'order': order.code,
                'charge': charge_id
            })
        )
    elif order.status in (Order.STATUS_PENDING, Order.STATUS_EXPIRED) and charge['status'] == 'succeeded' and not is_refund:
        try:
            mark_order_paid(order, user=None)
        except Quota.QuotaExceededException:
            if not RequiredAction.objects.filter(event=request.event, action_type='pretix.plugins.stripe.overpaid',
                                                 data__icontains=order.code).exists():
                RequiredAction.objects.create(
                    event=request.event, action_type='pretix.plugins.stripe.overpaid', data=json.dumps({
                        'order': order.code,
                        'charge': charge.id
                    })
                )

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
