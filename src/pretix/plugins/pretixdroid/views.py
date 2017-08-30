import json
import logging

import dateutil.parser
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import (
    HttpResponseForbidden, HttpResponseNotFound, JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, View

from pretix.base.models import Checkin, Event, Order, OrderPosition
from pretix.base.models.event import SubEvent
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.helpers.urls import build_absolute_uri
from pretix.multidomain.urlreverse import (
    build_absolute_uri as event_absolute_uri,
)
from pretix.plugins.pretixdroid.forms import AppConfigurationForm
from pretix.plugins.pretixdroid.models import AppConfiguration

logger = logging.getLogger('pretix.plugins.pretixdroid')
API_VERSION = 3


class ConfigCodeView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixplugins/pretixdroid/configuration_code.html'
    permission = 'can_change_orders'

    def get(self, request, **kwargs):
        try:
            self.object = self.request.event.appconfiguration_set.get(pk=kwargs.get("config"))
        except AppConfiguration.DoesNotExist:
            messages.error(request, _('The selected configuration does not exist.'))
            return redirect(reverse('plugins:pretixdroid:config', kwargs={
                'organizer': self.request.event.organizer.slug,
                'event': self.request.event.slug,
            }))
        return super().get(request, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        url = build_absolute_uri('plugins:pretixdroid:api.redeem', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })
        if self.object.subevent:
            url = build_absolute_uri('plugins:pretixdroid:api.redeem', kwargs={
                'organizer': self.request.event.organizer.slug,
                'event': self.request.event.slug,
                'subevent': self.object.subevent.pk
            })

        ctx['qrdata'] = json.dumps({
            'version': API_VERSION,
            'url': url[:-7],  # the slice removes the redeem/ part at the end
            'key': self.object.key,
            'allow_search': self.object.allow_search,
            'show_info': self.object.show_info
        })
        return ctx


class ConfigView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixplugins/pretixdroid/configuration.html'
    permission = 'can_change_orders'

    @cached_property
    def add_form(self):
        return AppConfigurationForm(
            event=self.request.event,
            instance=AppConfiguration(event=self.request.event),
            data=self.request.POST if self.request.method == "POST" and "add" in self.request.POST else None
        )

    def post(self, request, *args, **kwargs):
        if "add" in self.request.POST and self.add_form.is_valid():
            self.add_form.save()
            self.request.event.log_action('pretix.plugins.pretixdroid.config.added', user=self.request.user,
                                          data=dict(self.add_form.cleaned_data))
            return redirect(reverse('plugins:pretixdroid:config.code', kwargs={
                'organizer': self.request.event.organizer.slug,
                'event': self.request.event.slug,
                'config': self.add_form.instance.pk
            }))
        elif "delete" in self.request.POST:
            try:
                ac = self.request.event.appconfiguration_set.get(pk=request.POST.get("delete"))
                self.request.event.log_action('pretix.plugins.pretixdroid.config.deleted', user=self.request.user,
                                              data={'id': ac.pk})
                ac.delete()
                messages.success(request, _('The selected configuration has been deleted.'))
            except AppConfiguration.DoesNotExist:
                messages.error(request, _('The selected configuration does not exist.'))
            return redirect(reverse('plugins:pretixdroid:config', kwargs={
                'organizer': self.request.event.organizer.slug,
                'event': self.request.event.slug,
            }))
        else:
            return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['add_form'] = self.add_form
        ctx['configs'] = self.request.event.appconfiguration_set.prefetch_related('items')
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

        try:
            self.config = self.event.appconfiguration_set.get(key=request.GET.get("key", "-unset-"))
        except AppConfiguration.DoesNotExist:
            return HttpResponseForbidden('Invalid key')

        self.subevent = None
        if self.event.has_subevents:
            if self.config.subevent:
                self.subevent = self.config.subevent
            elif 'subevent' in kwargs:
                self.subevent = get_object_or_404(SubEvent, event=self.event, pk=kwargs['subevent'])
            else:
                return HttpResponseForbidden('No subevent selected.')
        else:
            if 'subevent' in kwargs:
                return HttpResponseForbidden('Subevents not enabled.')

        return super().dispatch(request, **kwargs)


class ApiRedeemView(ApiView):
    def post(self, request, **kwargs):
        secret = request.POST.get('secret', '!INVALID!')
        force = request.POST.get('force', 'false') in ('true', 'True')
        nonce = request.POST.get('nonce')
        response = {
            'version': API_VERSION
        }

        if 'datetime' in request.POST:
            dt = dateutil.parser.parse(request.POST.get('datetime'))
        else:
            dt = now()

        try:
            with transaction.atomic():
                created = False
                op = OrderPosition.objects.select_related('item', 'variation', 'order', 'addon_to').get(
                    order__event=self.event, secret=secret, subevent=self.subevent
                )
                if not self.config.all_items and op.item_id not in [i.pk for i in self.config.items.all()]:
                    response['status'] = 'error'
                    response['reason'] = 'product'
                elif op.order.status == Order.STATUS_PAID or force:
                    ci, created = Checkin.objects.get_or_create(position=op, defaults={
                        'datetime': dt,
                        'nonce': nonce,
                    })
                else:
                    response['status'] = 'error'
                    response['reason'] = 'unpaid'

            if 'status' not in response:
                if created or (nonce and nonce == ci.nonce):
                    response['status'] = 'ok'
                    if created:
                        op.order.log_action('pretix.plugins.pretixdroid.scan', data={
                            'position': op.id,
                            'positionid': op.positionid,
                            'first': True,
                            'forced': op.order.status != Order.STATUS_PAID,
                            'datetime': dt,
                        })
                else:
                    if force:
                        response['status'] = 'ok'
                    else:
                        response['status'] = 'error'
                        response['reason'] = 'already_redeemed'
                    op.order.log_action('pretix.plugins.pretixdroid.scan', data={
                        'position': op.id,
                        'positionid': op.positionid,
                        'first': False,
                        'forced': force,
                        'datetime': dt,
                    })

            response['data'] = serialize_op(op, redeemed=op.order.status == Order.STATUS_PAID or force)

        except OrderPosition.DoesNotExist:
            response['status'] = 'error'
            response['reason'] = 'unknown_ticket'

        return JsonResponse(response)


def serialize_op(op, redeemed):
    name = op.attendee_name
    if not name and op.addon_to:
        name = op.addon_to.attendee_name
    if not name:
        try:
            name = op.order.invoice_address.name
        except:
            pass
    return {
        'secret': op.secret,
        'order': op.order.code,
        'item': str(op.item),
        'item_id': op.item_id,
        'variation': str(op.variation) if op.variation else None,
        'variation_id': op.variation_id,
        'attendee_name': name,
        'attention': op.item.checkin_attention,
        'redeemed': redeemed,
        'paid': op.order.status == Order.STATUS_PAID,
    }


class ApiSearchView(ApiView):
    def get(self, request, **kwargs):
        query = request.GET.get('query', '!INVALID!')
        response = {
            'version': API_VERSION
        }

        if len(query) >= 4:
            qs = OrderPosition.objects.select_related('item', 'variation', 'order', 'addon_to', 'order__invoice_address')
            if not self.config.allow_search:
                ops = qs.filter(
                    Q(order__event=self.event) & Q(secret__istartswith=query) & Q(subevent=self.subevent)
                ).annotate(checkin_cnt=Count('checkins'))[:25]
            else:
                ops = qs.filter(
                    Q(order__event=self.event)
                    & Q(
                        Q(secret__istartswith=query) | Q(attendee_name__icontains=query) | Q(order__code__istartswith=query)
                        | Q(order__invoice_address__name__icontains=query)
                    )
                    & Q(subevent=self.subevent)
                ).annotate(checkin_cnt=Count('checkins'))[:25]

            response['results'] = [serialize_op(op, bool(op.checkin_cnt)) for op in ops]
        else:
            response['results'] = []

        return JsonResponse(response)


class ApiDownloadView(ApiView):
    def get(self, request, **kwargs):
        response = {
            'version': API_VERSION
        }

        ops = OrderPosition.objects.select_related('item', 'variation', 'order', 'addon_to').filter(
            Q(order__event=self.event) & Q(subevent=self.subevent)
        )
        if not self.config.all_items:
            ops = ops.filter(item__in=self.config.items.all())

        ops = ops.annotate(checkin_cnt=Count('checkins'))
        response['results'] = [serialize_op(op, bool(op.checkin_cnt)) for op in ops]

        return JsonResponse(response)


class ApiStatusView(ApiView):
    def get(self, request, **kwargs):
        ev = self.subevent or self.event
        response = {
            'version': API_VERSION,
            'event': {
                'name': str(ev.name),
                'slug': self.event.slug,
                'organizer': {
                    'name': str(self.event.organizer),
                    'slug': self.event.organizer.slug
                },
                'subevent': self.subevent.pk if self.subevent else str(self.event),
                'date_from': ev.date_from,
                'date_to': ev.date_to,
                'timezone': self.event.settings.timezone,
                'url': event_absolute_uri(self.event, 'presale:event.index')
            },
            'checkins': Checkin.objects.filter(
                position__order__event=self.event, position__subevent=self.subevent
            ).count(),
            'total': OrderPosition.objects.filter(
                order__event=self.event, order__status=Order.STATUS_PAID, subevent=self.subevent
            ).count()
        }

        op_by_item = {
            p['item']: p['cnt']
            for p in OrderPosition.objects.filter(
                order__event=self.event,
                order__status=Order.STATUS_PAID,
                subevent=self.subevent
            ).order_by().values('item').annotate(cnt=Count('id'))
        }
        op_by_variation = {
            p['variation']: p['cnt']
            for p in OrderPosition.objects.filter(
                order__event=self.event,
                order__status=Order.STATUS_PAID,
                subevent=self.subevent
            ).order_by().values('variation').annotate(cnt=Count('id'))
        }
        c_by_item = {
            p['position__item']: p['cnt']
            for p in Checkin.objects.filter(
                position__order__event=self.event,
                position__order__status=Order.STATUS_PAID,
                position__subevent=self.subevent
            ).order_by().values('position__item').annotate(cnt=Count('id'))
        }
        c_by_variation = {
            p['position__variation']: p['cnt']
            for p in Checkin.objects.filter(
                position__order__event=self.event,
                position__order__status=Order.STATUS_PAID,
                position__subevent=self.subevent
            ).order_by().values('position__variation').annotate(cnt=Count('id'))
        }

        response['items'] = []
        for item in self.event.items.order_by('pk').prefetch_related('variations'):
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
