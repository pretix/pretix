import json
import logging
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pretix.base.models import Order, Event
from pretix.plugins.stripe.payment import Stripe
import stripe


logger = logging.getLogger('pretix.plugins.stripe')


@csrf_exempt
@require_POST
def webhook(request):
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
        event = Event.objects.current.get(identity=metadata['event'])
    except Event.DoesNotExist:
        return HttpResponse('Event not found', status=200)

    try:
        order = Order.objects.current.get(identity=metadata['order'])
    except Order.DoesNotExist:
        return HttpResponse('Order not found', status=200)

    prov = Stripe(event)
    prov._init_api()

    try:
        charge = stripe.Charge.retrieve(charge['id'])
    except stripe.error.StripeError as err:
        logger.error('Stripe error on webhook: %s Event data: %s' % (str(err), str(event_json)))
        return HttpResponse('StripeError', status=500)

    if charge['refunds']['total_count'] > 0 and order.status == Order.STATUS_PAID:
        order.mark_refunded()

    return HttpResponse(status=200)
