import json
import logging

import stripe
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from pretix.base.models import Event, Order
from pretix.base.services.orders import mark_order_refunded
from pretix.plugins.stripe.payment import Stripe

logger = logging.getLogger('pretix.plugins.stripe')


@csrf_exempt
@require_POST
def webhook(request, *args, **kwargs):
    event_json = json.loads(request.body.decode('utf-8'))
    event_type = event_json['type']
    if event_type != 'charge.refunded':
        # Not interested
        return HttpResponse('Event is not a refund', status=200)

    charge = event_json['data']['object']
    if charge['object'] != 'charge':
        return HttpResponse('Object is not a charge', status=200)

    metadata = charge['metadata']
    if 'event' not in metadata:
        return HttpResponse('Event not given', status=200)

    try:
        event = Event.objects.get(id=metadata['event'])
    except Event.DoesNotExist:
        return HttpResponse('Event not found', status=200)

    try:
        order = Order.objects.get(id=metadata['order'])
    except Order.DoesNotExist:
        return HttpResponse('Order not found', status=200)

    prov = Stripe(event)
    prov._init_api()

    order.log_action('pretix.plugins.stripe.event', data=event_json)

    try:
        charge = stripe.Charge.retrieve(charge['id'])
    except stripe.error.StripeError as err:
        logger.error('Stripe error on webhook: %s Event data: %s' % (str(err), str(event_json)))
        return HttpResponse('StripeError', status=500)

    if charge['refunds']['total_count'] > 0 and order.status == Order.STATUS_PAID:
        mark_order_refunded(order)

    return HttpResponse(status=200)
