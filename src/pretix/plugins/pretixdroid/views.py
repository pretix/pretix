import json
import logging
import urllib.parse

import dateutil.parser
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, OuterRef, Prefetch, Q, Subquery
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

from pretix.base.models import (
    Checkin, Event, Order, OrderPosition, Question, QuestionOption,
)
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

        data = {
            'version': API_VERSION,
            'url': url[:-7],  # the slice removes the redeem/ part at the end
            'key': self.object.key,
            'allow_search': self.object.allow_search,
            'show_info': self.object.show_info
        }
        ctx['config'] = self.object
        ctx['query'] = urllib.parse.urlencode(data, safe=':/')
        ctx['qrdata'] = json.dumps(data)
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
        ctx['configs'] = self.request.event.appconfiguration_set.select_related('list').prefetch_related('items')
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
            if self.config.list.subevent:
                self.subevent = self.config.list.subevent
                if 'subevent' in kwargs and kwargs['subevent'] != str(self.subevent.pk):
                    return HttpResponseForbidden('Invalid subevent selected.')
            elif 'subevent' in kwargs:
                self.subevent = get_object_or_404(SubEvent, event=self.event, pk=kwargs['subevent'])
            else:
                return HttpResponseForbidden('No subevent selected.')
        else:
            if 'subevent' in kwargs:
                return HttpResponseForbidden('Subevents not enabled.')

        return super().dispatch(request, **kwargs)


class ApiRedeemView(ApiView):
    def _save_answers(self, op, answers, given_answers):
        for q, a in given_answers.items():
            if not a:
                if q in answers:
                    answers[q].delete()
                else:
                    continue
            if isinstance(a, QuestionOption):
                if q in answers:
                    qa = answers[q]
                    qa.answer = str(a.answer)
                    qa.save()
                    qa.options.clear()
                else:
                    qa = op.answers.create(question=q, answer=str(a.answer))
                qa.options.add(a)
            elif isinstance(a, list):
                if q in answers:
                    qa = answers[q]
                    qa.answer = ", ".join([str(o) for o in a])
                    qa.save()
                    qa.options.clear()
                else:
                    qa = op.answers.create(question=q, answer=", ".join([str(o) for o in a]))
                qa.options.add(*a)
            else:
                if q in answers:
                    qa = answers[q]
                    qa.answer = str(a)
                    qa.save()
                else:
                    op.answers.create(question=q, answer=str(a))

    def post(self, request, **kwargs):
        secret = request.POST.get('secret', '!INVALID!')
        force = request.POST.get('force', 'false') in ('true', 'True')
        ignore_unpaid = request.POST.get('ignore_unpaid', 'false') in ('true', 'True')
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
                op = OrderPosition.objects.select_related(
                    'item', 'variation', 'order', 'addon_to'
                ).prefetch_related(
                    'item__questions',
                    Prefetch(
                        'item__questions',
                        queryset=Question.objects.filter(ask_during_checkin=True),
                        to_attr='checkin_questions'
                    ),
                    'answers'
                ).get(
                    order__event=self.event, secret=secret, subevent=self.subevent
                )
                answers = {a.question: a for a in op.answers.all()}
                require_answers = []
                given_answers = {}
                for q in op.item.checkin_questions:
                    if 'answer_{}'.format(q.pk) in request.POST:
                        try:
                            given_answers[q] = q.clean_answer(request.POST.get('answer_{}'.format(q.pk)))
                            continue
                        except ValidationError:
                            pass

                    if q in answers:
                        continue

                    require_answers.append(serialize_question(q))

                self._save_answers(op, answers, given_answers)

                if not self.config.list.all_products and op.item_id not in [i.pk for i in
                                                                            self.config.list.limit_products.all()]:
                    response['status'] = 'error'
                    response['reason'] = 'product'
                elif not self.config.all_items and op.item_id not in [i.pk for i in self.config.items.all()]:
                    response['status'] = 'error'
                    response['reason'] = 'product'
                elif op.order.status != Order.STATUS_PAID and not force and not (
                    ignore_unpaid and self.config.list.include_pending and op.order.status == Order.STATUS_PENDING
                ):
                    response['status'] = 'error'
                    response['reason'] = 'unpaid'
                elif require_answers and not force and request.POST.get('questions_supported'):
                    response['status'] = 'incomplete'
                    response['questions'] = require_answers
                else:
                    ci, created = Checkin.objects.get_or_create(position=op, list=self.config.list, defaults={
                        'datetime': dt,
                        'nonce': nonce,
                    })

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
                            'list': self.config.list.pk
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
                        'list': self.config.list.pk
                    })

            response['data'] = serialize_op(op, redeemed=op.order.status == Order.STATUS_PAID or force,
                                            clist=self.config.list)

        except OrderPosition.DoesNotExist:
            response['status'] = 'error'
            response['reason'] = 'unknown_ticket'

        return JsonResponse(response)


def serialize_question(q, items=False):
    d = {
        'id': q.pk,
        'type': q.type,
        'question': str(q.question),
        'required': q.required,
        'position': q.position,
        'options': [
            {
                'id': o.pk,
                'answer': str(o.answer)
            } for o in q.options.all()
        ] if q.type in ('C', 'M') else []
    }
    if items:
        d['items'] = [i.pk for i in q.items.all()]
    return d


def serialize_op(op, redeemed, clist):
    name = op.attendee_name
    if not name and op.addon_to:
        name = op.addon_to.attendee_name
    if not name:
        try:
            name = op.order.invoice_address.name
        except:
            pass
    checkin_allowed = (
        op.order.status == Order.STATUS_PAID
        or (
            op.order.status == Order.STATUS_PENDING
            and clist.include_pending
        )
    )
    return {
        'secret': op.secret,
        'order': op.order.code,
        'item': str(op.item),
        'item_id': op.item_id,
        'variation': str(op.variation) if op.variation else None,
        'variation_id': op.variation_id,
        'attendee_name': name,
        'attention': op.item.checkin_attention or op.order.checkin_attention,
        'redeemed': redeemed,
        'paid': op.order.status == Order.STATUS_PAID,
        'checkin_allowed': checkin_allowed
    }


class ApiSearchView(ApiView):
    def get(self, request, **kwargs):
        query = request.GET.get('query', '!INVALID!')
        response = {
            'version': API_VERSION
        }

        if len(query) >= 4:
            cqs = Checkin.objects.filter(
                position_id=OuterRef('pk'),
                list_id=self.config.list.pk
            ).order_by().values('position_id').annotate(
                m=Max('datetime')
            ).values('m')

            qs = OrderPosition.objects.filter(
                order__event=self.event,
                subevent=self.config.list.subevent
            ).annotate(
                last_checked_in=Subquery(cqs)
            ).select_related('item', 'variation', 'order', 'order__invoice_address', 'addon_to')

            if not self.config.list.all_products:
                qs = qs.filter(item__in=self.config.list.limit_products.values_list('id', flat=True))

            if not self.config.all_items:
                qs = qs.filter(item__in=self.config.items.all())

            if not self.config.allow_search:
                ops = qs.filter(
                    Q(secret__istartswith=query)
                )[:25]
            else:
                ops = qs.filter(
                    Q(secret__istartswith=query)
                    | Q(attendee_name__icontains=query)
                    | Q(addon_to__attendee_name__icontains=query)
                    | Q(order__code__istartswith=query)
                    | Q(order__invoice_address__name__icontains=query)
                )[:25]

            response['results'] = [serialize_op(op, bool(op.last_checked_in), self.config.list) for op in ops]
        else:
            response['results'] = []

        return JsonResponse(response)


class ApiDownloadView(ApiView):
    def get(self, request, **kwargs):
        response = {
            'version': API_VERSION
        }

        cqs = Checkin.objects.filter(
            position_id=OuterRef('pk'),
            list_id=self.config.list.pk
        ).order_by().values('position_id').annotate(
            m=Max('datetime')
        ).values('m')

        qs = OrderPosition.objects.filter(
            order__event=self.event,
            order__status__in=[Order.STATUS_PAID] + ([Order.STATUS_PENDING] if self.config.list.include_pending else
                                                     []),
            subevent=self.config.list.subevent
        ).annotate(
            last_checked_in=Subquery(cqs)
        ).select_related('item', 'variation', 'order', 'addon_to')

        if not self.config.list.all_products:
            qs = qs.filter(item__in=self.config.list.limit_products.values_list('id', flat=True))

        if not self.config.all_items:
            qs = qs.filter(item__in=self.config.items.all())

        response['results'] = [serialize_op(op, bool(op.last_checked_in), self.config.list) for op in qs]

        questions = self.event.questions.filter(ask_during_checkin=True).prefetch_related('items', 'options')
        response['questions'] = [serialize_question(q, items=True) for q in questions]
        return JsonResponse(response)


class ApiStatusView(ApiView):
    def get(self, request, **kwargs):

        cqs = Checkin.objects.filter(
            position__order__event=self.event, position__subevent=self.subevent,
            position__order__status__in=[Order.STATUS_PAID] + ([Order.STATUS_PENDING] if
                                                               self.config.list.include_pending else []),
            list=self.config.list
        )
        pqs = OrderPosition.objects.filter(
            order__event=self.event,
            order__status__in=[Order.STATUS_PAID] + ([Order.STATUS_PENDING] if self.config.list.include_pending else
                                                     []),
            subevent=self.subevent,
        )
        if not self.config.list.all_products:
            pqs = pqs.filter(item__in=self.config.list.limit_products.values_list('id', flat=True))

        ev = self.subevent or self.event
        response = {
            'version': API_VERSION,
            'event': {
                'name': str(ev.name),
                'list': self.config.list.name,
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
            'checkins': cqs.count(),
            'total': pqs.count()
        }

        op_by_item = {
            p['item']: p['cnt']
            for p in pqs.order_by().values('item').annotate(cnt=Count('id'))
        }
        op_by_variation = {
            p['variation']: p['cnt']
            for p in pqs.order_by().values('variation').annotate(cnt=Count('id'))
        }
        c_by_item = {
            p['position__item']: p['cnt']
            for p in cqs.order_by().values('position__item').annotate(cnt=Count('id'))
        }
        c_by_variation = {
            p['position__variation']: p['cnt']
            for p in cqs.order_by().values('position__variation').annotate(cnt=Count('id'))
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
