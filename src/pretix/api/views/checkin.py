import django_filters
from django.db.models import F, Max, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import viewsets

from pretix.api.serializers.checkin import CheckinListSerializer
from pretix.api.serializers.order import OrderPositionSerializer
from pretix.api.views import RichOrderingFilter
from pretix.base.models import Checkin, CheckinList, Order, OrderPosition
from pretix.base.models.organizer import TeamAPIToken
from pretix.helpers.database import FixedOrderBy


class CheckinListFilter(FilterSet):
    class Meta:
        model = CheckinList
        fields = ['subevent']


class CheckinListViewSet(viewsets.ModelViewSet):
    serializer_class = CheckinListSerializer
    queryset = CheckinList.objects.none()
    filter_backends = (DjangoFilterBackend,)
    filter_class = CheckinListFilter
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
            api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
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
            api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
            data=self.request.data
        )

    def perform_destroy(self, instance):
        instance.log_action(
            'pretix.event.checkinlist.deleted',
            user=self.request.user,
            api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
        )
        super().perform_destroy(instance)


class OrderPositionFilter(FilterSet):
    order = django_filters.CharFilter(name='order', lookup_expr='code')
    has_checkin = django_filters.rest_framework.BooleanFilter(method='has_checkin_qs')
    attendee_name = django_filters.CharFilter(method='attendee_name_qs')

    def has_checkin_qs(self, queryset, name, value):
        return queryset.filter(last_checked_in__isnull=not value)

    def attendee_name_qs(self, queryset, name, value):
        return queryset.filter(Q(attendee_name=value) | Q(addon_to__attendee_name=value))

    class Meta:
        model = OrderPosition
        fields = ['item', 'variation', 'attendee_name', 'secret', 'order', 'has_checkin', 'addon_to', 'subevent']


class CheckinListPositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderPositionSerializer
    queryset = OrderPosition.objects.none()
    filter_backends = (DjangoFilterBackend, RichOrderingFilter)
    ordering = ('attendee_name', 'positionid')
    ordering_fields = (
        'order__code', 'order__datetime', 'positionid', 'attendee_name',
        'last_checked_in', 'order__email',
    )
    ordering_custom = {
        'attendee_name': {
            '_order': F('display_name').asc(nulls_first=True),
            'display_name': Coalesce('attendee_name', 'addon_to__attendee_name')
        },
        '-attendee_name': {
            '_order': F('display_name').desc(nulls_last=True),
            'display_name': Coalesce('attendee_name', 'addon_to__attendee_name')
        },
        'last_checked_in': {
            '_order': FixedOrderBy(F('last_checked_in'), nulls_first=True),
        },
        '-last_checked_in': {
            '_order': FixedOrderBy(F('last_checked_in'), nulls_last=True, descending=True),
        },
    }

    filter_class = OrderPositionFilter
    permission = 'can_view_orders'

    @cached_property
    def checkinlist(self):
        return get_object_or_404(CheckinList, event=self.request.event, pk=self.kwargs.get("list"))

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
        ).prefetch_related(
            Prefetch(
                lookup='checkins',
                queryset=Checkin.objects.filter(list_id=self.checkinlist.pk)
            )
        ).select_related('item', 'variation', 'order', 'addon_to')

        if not self.checkinlist.all_products:
            qs = qs.filter(item__in=self.checkinlist.limit_products.values_list('id', flat=True))

        return qs
