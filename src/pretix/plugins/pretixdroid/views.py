import json
import logging
import string

from django.http import (
    HttpResponseForbidden, HttpResponseNotFound, JsonResponse,
)
from django.utils.crypto import get_random_string
from django.views.generic import TemplateView, View

from pretix.base.models import Event, Order, OrderPosition
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.helpers.urls import build_absolute_uri

logger = logging.getLogger('pretix.plugins.pretixdroid')


class ConfigView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixplugins/pretixdroid/configuration.html'
    permission = 'can_change_orders'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        key = self.request.event.settings.get('pretixdroid_key')
        if not key or 'flush_key' in self.request.GET:
            key = get_random_string(length=32, allowed_chars=string.ascii_uppercase + string.ascii_lowercase + string.digits)
            self.request.event.settings.set('pretixdroid_key', key)

        ctx['qrdata'] = json.dumps({
            'version': 1,
            'url': build_absolute_uri('plugins:pretixdroid:api', kwargs={
                'organizer': self.request.event.organizer.slug,
                'event': self.request.event.slug
            }),
            'key': key
        })
        return ctx


class ApiView(View):
    def get(self, request, **kwargs):
        try:
            event = Event.objects.get(
                slug=self.kwargs['event'],
                organizer__slug=self.kwargs['organizer']
            )
        except Event.DoesNotExist:
            return HttpResponseNotFound('Unknown event')

        if (not event.settings.get('pretixdroid_key')
                or event.settings.get('pretixdroid_key') != request.GET.get('key', '')):
            return HttpResponseForbidden('Invalid key')

        ops = OrderPosition.objects.filter(
            order__event=event, order__status=Order.STATUS_PAID,
        ).select_related('item', 'variation')
        data = [
            {
                'secret': op.secret,
                'item': str(op.item),
                'variation': str(op.variation) if op.variation else None,
                'attendee_name': op.attendee_name
            }
            for op in ops
        ]
        return JsonResponse({'data': data, 'version': 1})
