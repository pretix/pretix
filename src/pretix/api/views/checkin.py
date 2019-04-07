from django.core.exceptions import ValidationError
from django.db.models import Count, F, Max, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.fields import DateTimeField
from rest_framework.response import Response

from pretix.api.serializers.checkin import CheckinListSerializer
from pretix.api.serializers.item import QuestionSerializer
from pretix.api.serializers.order import OrderPositionSerializer
from pretix.api.views import RichOrderingFilter
from pretix.api.views.order import OrderPositionFilter
from pretix.base.models import (
    Checkin, CheckinList, Event, Order, OrderPosition,
)
from pretix.base.services.checkin import (
    CheckInError, RequiredQuestionsError, perform_checkin,
)
from pretix.helpers.database import FixedOrderBy


class CheckinListFilter(FilterSet):
    class Meta:
        model = CheckinList
        fields = ['subevent']


class CheckinListViewSet(viewsets.ModelViewSet):
    serializer_class = CheckinListSerializer
    queryset = CheckinList.objects.none()
    filter_backends = (DjangoFilterBackend,)
    filterset_class = CheckinListFilter
    permission = 'can_view_orders'
    write_permission = 'can_change_event_settings'

    def get_queryset(self):
        qs = self.request.event.checkin_lists.prefetch_related(
            'limit_products',
        )
        qs = CheckinList.annotate_with_numbers(qs, self.request.event)
        return qs

    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.checkinlist.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        return ctx

    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.checkinlist.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def perform_destroy(self, instance):
        instance.log_action(
            'pretix.event.checkinlist.deleted',
            user=self.request.user,
            auth=self.request.auth,
        )
        super().perform_destroy(instance)

    @action(detail=True, methods=['GET'])
    def status(self, *args, **kwargs):
        clist = self.get_object()
        cqs = Checkin.objects.filter(
            position__order__event=clist.event,
            position__order__status__in=[Order.STATUS_PAID] + ([Order.STATUS_PENDING] if clist.include_pending else []),
            list=clist
        )
        pqs = OrderPosition.objects.filter(
            order__event=clist.event,
            order__status__in=[Order.STATUS_PAID] + ([Order.STATUS_PENDING] if clist.include_pending else []),
            subevent=clist.subevent,
        )
        if not clist.all_products:
            pqs = pqs.filter(item__in=clist.limit_products.values_list('id', flat=True))

        ev = clist.subevent or clist.event
        response = {
            'event': {
                'name': str(ev.name),
            },
            'checkin_count': cqs.count(),
            'position_count': pqs.count()
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

        if not clist.all_products:
            items = clist.limit_products
        else:
            items = clist.event.items

        response['items'] = []
        for item in items.order_by('category__position', 'position', 'pk').prefetch_related('variations'):
            i = {
                'id': item.pk,
                'name': str(item),
                'admission': item.admission,
                'checkin_count': c_by_item.get(item.pk, 0),
                'position_count': op_by_item.get(item.pk, 0),
                'variations': []
            }
            for var in item.variations.all():
                i['variations'].append({
                    'id': var.pk,
                    'value': str(var),
                    'checkin_count': c_by_variation.get(var.pk, 0),
                    'position_count': op_by_variation.get(var.pk, 0),
                })
            response['items'].append(i)

        return Response(response)


class CheckinOrderPositionFilter(OrderPositionFilter):

    def has_checkin_qs(self, queryset, name, value):
        return queryset.filter(last_checked_in__isnull=not value)


class CheckinListPositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderPositionSerializer
    queryset = OrderPosition.objects.none()
    filter_backends = (DjangoFilterBackend, RichOrderingFilter)
    ordering = ('attendee_name_cached', 'positionid')
    ordering_fields = (
        'order__code', 'order__datetime', 'positionid', 'attendee_name',
        'last_checked_in', 'order__email',
    )
    ordering_custom = {
        'attendee_name': {
            '_order': F('display_name').asc(nulls_first=True),
            'display_name': Coalesce('attendee_name_cached', 'addon_to__attendee_name_cached')
        },
        '-attendee_name': {
            '_order': F('display_name').desc(nulls_last=True),
            'display_name': Coalesce('attendee_name_cached', 'addon_to__attendee_name_cached')
        },
        'last_checked_in': {
            '_order': FixedOrderBy(F('last_checked_in'), nulls_first=True),
        },
        '-last_checked_in': {
            '_order': FixedOrderBy(F('last_checked_in'), nulls_last=True, descending=True),
        },
    }

    filterset_class = CheckinOrderPositionFilter
    permission = 'can_view_orders'
    write_permission = 'can_change_orders'

    @cached_property
    def checkinlist(self):
        try:
            return get_object_or_404(CheckinList, event=self.request.event, pk=self.kwargs.get("list"))
        except ValueError:
            raise Http404()

    def get_queryset(self):
        cqs = Checkin.objects.filter(
            position_id=OuterRef('pk'),
            list_id=self.checkinlist.pk
        ).order_by().values('position_id').annotate(
            m=Max('datetime')
        ).values('m')

        qs = OrderPosition.objects.filter(
            order__event=self.request.event,
            order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING] if self.checkinlist.include_pending else [Order.STATUS_PAID],
            subevent=self.checkinlist.subevent
        ).annotate(
            last_checked_in=Subquery(cqs)
        )
        if self.request.query_params.get('pdf_data', 'false') == 'true':
            qs = qs.prefetch_related(
                Prefetch(
                    lookup='checkins',
                    queryset=Checkin.objects.filter(list_id=self.checkinlist.pk)
                ),
                'checkins', 'answers', 'answers__options', 'answers__question',
                Prefetch('addons', OrderPosition.objects.select_related('item', 'variation')),
                Prefetch('order', Order.objects.select_related('invoice_address').prefetch_related(
                    Prefetch(
                        'event',
                        Event.objects.select_related('organizer')
                    ),
                    Prefetch(
                        'positions',
                        OrderPosition.objects.prefetch_related(
                            'checkins', 'item', 'variation', 'answers', 'answers__options', 'answers__question',
                        )
                    )
                ))
            ).select_related(
                'item', 'variation', 'item__category', 'addon_to'
            )
        else:
            qs = qs.prefetch_related(
                Prefetch(
                    lookup='checkins',
                    queryset=Checkin.objects.filter(list_id=self.checkinlist.pk)
                ),
                'answers', 'answers__options', 'answers__question',
                Prefetch('addons', OrderPosition.objects.select_related('item', 'variation'))
            ).select_related('item', 'variation', 'order', 'addon_to', 'order__invoice_address')

        if not self.checkinlist.all_products:
            qs = qs.filter(item__in=self.checkinlist.limit_products.values_list('id', flat=True))

        return qs

    @action(detail=True, methods=['POST'])
    def redeem(self, *args, **kwargs):
        force = bool(self.request.data.get('force', False))
        ignore_unpaid = bool(self.request.data.get('ignore_unpaid', False))
        nonce = self.request.data.get('nonce')
        op = self.get_object()

        if 'datetime' in self.request.data:
            dt = DateTimeField().to_internal_value(self.request.data.get('datetime'))
        else:
            dt = now()

        given_answers = {}
        if 'answers' in self.request.data:
            aws = self.request.data.get('answers')
            for q in op.item.questions.filter(ask_during_checkin=True):
                if str(q.pk) in aws:
                    try:
                        given_answers[q] = q.clean_answer(aws[str(q.pk)])
                    except ValidationError:
                        pass

        try:
            perform_checkin(
                op=op,
                clist=self.checkinlist,
                given_answers=given_answers,
                force=force,
                ignore_unpaid=ignore_unpaid,
                nonce=nonce,
                datetime=dt,
                questions_supported=self.request.data.get('questions_supported', True),
                user=self.request.user,
                auth=self.request.auth,
            )
        except RequiredQuestionsError as e:
            return Response({
                'status': 'incomplete',
                'require_attention': op.item.checkin_attention or op.order.checkin_attention,
                'position': OrderPositionSerializer(op, context=self.get_serializer_context()).data,
                'questions': [
                    QuestionSerializer(q).data for q in e.questions
                ]
            }, status=400)
        except CheckInError as e:
            return Response({
                'status': 'error',
                'reason': e.code,
                'require_attention': op.item.checkin_attention or op.order.checkin_attention,
                'position': OrderPositionSerializer(op, context=self.get_serializer_context()).data
            }, status=400)
        else:
            return Response({
                'status': 'ok',
                'require_attention': op.item.checkin_attention or op.order.checkin_attention,
                'position': OrderPositionSerializer(op, context=self.get_serializer_context()).data
            }, status=201)

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        if self.kwargs['pk'].isnumeric():
            obj = get_object_or_404(queryset, Q(pk=self.kwargs['pk']) | Q(secret=self.kwargs['pk']))
        else:
            obj = get_object_or_404(queryset, secret=self.kwargs['pk'])
        return obj
