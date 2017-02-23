import json
import logging
import string

from django.db import transaction
from django.db.models import Count, Q
from django.http import (
    HttpResponseForbidden, HttpResponseNotFound, JsonResponse,
)
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, View

from pretix.base.models import Checkin, Event, Order, OrderPosition
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.helpers.urls import build_absolute_uri
from pretix.multidomain.urlreverse import \
    build_absolute_uri as event_absolute_uri

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
                    op.order.log_action('pretix.plugins.pretixdroid.scan', data={
                        'position': op.id,
                        'positionid': op.positionid,
                        'first': True,
                    })
                else:
                    response['status'] = 'error'
                    response['reason'] = 'already_redeemed'
                    op.order.log_action('pretix.plugins.pretixdroid.scan', data={
                        'position': op.id,
                        'positionid': op.positionid,
                        'first': False,
                    })

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


class ApiSearchView(ApiView):
    def get(self, request, **kwargs):
        query = request.GET.get('query', '!INVALID!')
        response = {
            'version': API_VERSION
        }

        if len(query) >= 4:
            ops = OrderPosition.objects.select_related('item', 'variation', 'order').filter(
                Q(order__event=self.event)
                & Q(
                    Q(secret__istartswith=query) | Q(attendee_name__icontains=query) | Q(order__code__istartswith=query)
                )
            ).prefetch_related('checkins')[:25]

            response['results'] = [
                {
                    'secret': op.secret,
                    'order': op.order.code,
                    'item': str(op.item),
                    'variation': str(op.variation) if op.variation else None,
                    'attendee_name': op.attendee_name,
                    'redeemed': bool(op.checkins.all()),
                    'paid': op.order.status == Order.STATUS_PAID,
                } for op in ops
            ]
        else:
            response['results'] = []

        return JsonResponse(response)


class ApiStatusView(ApiView):
    def get(self, request, **kwargs):
        response = {
            'version': API_VERSION,
            'event': {
                'name': str(self.event),
                'slug': self.event.slug,
                'organizer': {
                    'name': str(self.event.organizer),
                    'slug': self.event.organizer.slug
                },
                'date_from': self.event.date_from,
                'date_to': self.event.date_to,
                'timezone': self.event.settings.timezone,
                'url': event_absolute_uri(self.event, 'presale:event.index')
            },
            'checkins': Checkin.objects.filter(
                position__order__event=self.event
            ).count(),
            'total': OrderPosition.objects.filter(
                order__event=self.event, order__status=Order.STATUS_PAID
            ).count()
        }

        op_by_item = {
            p['item']: p['cnt']
            for p in OrderPosition.objects.filter(
                order__event=self.event,
                order__status=Order.STATUS_PAID
            ).order_by().values('item').annotate(cnt=Count('id'))
        }
        op_by_variation = {
            p['variation']: p['cnt']
            for p in OrderPosition.objects.filter(
                order__event=self.event,
                order__status=Order.STATUS_PAID
            ).order_by().values('variation').annotate(cnt=Count('id'))
        }
        c_by_item = {
            p['position__item']: p['cnt']
            for p in Checkin.objects.filter(
                position__order__event=self.event,
                position__order__status=Order.STATUS_PAID
            ).order_by().values('position__item').annotate(cnt=Count('id'))
        }
        c_by_variation = {
            p['position__variation']: p['cnt']
            for p in Checkin.objects.filter(
                position__order__event=self.event,
                position__order__status=Order.STATUS_PAID
            ).order_by().values('position__variation').annotate(cnt=Count('id'))
        }

        response['items'] = []
        for item in self.event.items.prefetch_related('variations'):
            i = {
                'id': item.pk,
                'name': str(item),
                'admission': item.admission,
                'checkins': c_by_item.get(item.pk, 0),
                'total': op_by_item.get(item.pk, 0),
                'variations': []
            }
            for var in item.variations.all():
                i['variations'].append({
                    'id': var.pk,
                    'name': str(var),
                    'checkins': c_by_variation.get(var.pk, 0),
                    'total': op_by_variation.get(var.pk, 0),
                })
            response['items'].append(i)

        return JsonResponse(response)
