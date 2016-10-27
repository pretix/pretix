import json
import logging

import stripe
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from pretix.base.models import Order
from pretix.base.services.orders import mark_order_refunded
from pretix.plugins.stripe.payment import Stripe
from pretix.presale.utils import event_view

logger = logging.getLogger('pretix.plugins.stripe')


@csrf_exempt
@require_POST
@event_view
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
        order = request.event.orders.get(id=metadata['order'])
    except Order.DoesNotExist:
        return HttpResponse('Order not found', status=200)

    order.log_action('pretix.plugins.stripe.event', data=event_json)

    if order.status == Order.STATUS_PAID and (charge['refunds']['total_count'] or charge['dispute']):
        mark_order_refunded(order, user=None)

    return HttpResponse(status=200)
