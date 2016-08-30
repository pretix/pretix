import json
import logging
import string

from django.db import transaction
from django.http import (
    HttpResponseForbidden, HttpResponseNotFound, JsonResponse,
)
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, View

from pretix.base.models import Event, Order, OrderPosition
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.helpers.urls import build_absolute_uri
from pretix.plugins.pretixdroid.models import Checkin

logger = logging.getLogger('pretix.plugins.pretixdroid')
API_VERSION = 2


class ConfigView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixplugins/pretixdroid/configuration.html'
    permission = 'can_change_orders'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        key = self.request.event.settings.get('pretixdroid_key')
        if not key or 'flush_key' in self.request.GET:
            key = get_random_string(length=32,
                                    allowed_chars=string.ascii_uppercase + string.ascii_lowercase + string.digits)
            self.request.event.settings.set('pretixdroid_key', key)

        ctx['qrdata'] = json.dumps({
            'version': API_VERSION,
            'url': build_absolute_uri('plugins:pretixdroid:api.redeem', kwargs={
                'organizer': self.request.event.organizer.slug,
                'event': self.request.event.slug
            })[:-7],  # the slice removes the redeem/ part at the end
            'key': key
        })
        return ctx


class ApiView(View):

    @method_decorator(csrf_exempt)
    def dispatch(self, request, **kwargs):
        try:
            self.event = Event.objects.get(
                slug=self.kwargs['event'],
                organizer__slug=self.kwargs['organizer']
            )
        except Event.DoesNotExist:
            return HttpResponseNotFound('Unknown event')

        if (not self.event.settings.get('pretixdroid_key')
                or self.event.settings.get('pretixdroid_key') != request.GET.get('key', '')):
            return HttpResponseForbidden('Invalid key')

        return super().dispatch(request, **kwargs)


class ApiRedeemView(ApiView):
    def post(self, request, **kwargs):
        secret = request.POST.get('secret', '!INVALID!')
        response = {
            'version': API_VERSION
        }

        try:
            with transaction.atomic():
                created = False
                op = OrderPosition.objects.select_related('item', 'variation', 'order').get(
                    order__event=self.event, secret=secret
                )
                if op.order.status == Order.STATUS_PAID:
                    ci, created = Checkin.objects.get_or_create(position=op)
                else:
                    response['status'] = 'error'
                    response['reason'] = 'unpaid'

            if 'status' not in response:
                if created:
                    response['status'] = 'ok'
                else:
                    response['status'] = 'error'
                    response['reason'] = 'already_redeemed'

            response['data'] = {
                'secret': op.secret,
                'order': op.order.code,
                'item': str(op.item),
                'variation': str(op.variation) if op.variation else None,
                'attendee_name': op.attendee_name
            }

        except OrderPosition.DoesNotExist:
            response['status'] = 'error'
            response['reason'] = 'unknown_ticket'

        return JsonResponse(response)
