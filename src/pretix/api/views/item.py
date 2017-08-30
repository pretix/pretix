import django_filters
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import viewsets
from rest_framework.decorators import detail_route
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from pretix.api.serializers.item import (
    ItemCategorySerializer, ItemSerializer, QuestionSerializer,
    QuotaSerializer,
)
from pretix.base.models import Item, ItemCategory, Question, Quota


class ItemFilter(FilterSet):
    tax_rate = django_filters.CharFilter(method='tax_rate_qs')

    def tax_rate_qs(self, queryset, name, value):
        if value in ("0", "None", "0.00"):
            return queryset.filter(Q(tax_rule__isnull=True) | Q(tax_rule__rate=0))
        else:
            return queryset.filter(tax_rule__rate=value)

    class Meta:
        model = Item
        fields = ['active', 'category', 'admission', 'tax_rate', 'free_price']


class ItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ItemSerializer
    queryset = Item.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering_fields = ('id', 'position')
    ordering = ('position', 'id')
    filter_class = ItemFilter

    def get_queryset(self):
        return self.request.event.items.select_related('tax_rule').prefetch_related('variations', 'addons').all()


class ItemCategoryFilter(FilterSet):
    class Meta:
        model = ItemCategory
        fields = ['is_addon']


class ItemCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ItemCategorySerializer
    queryset = ItemCategory.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filter_class = ItemCategoryFilter
    ordering_fields = ('id', 'position')
    ordering = ('position', 'id')

    def get_queryset(self):
        return self.request.event.categories.all()


class QuestionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = QuestionSerializer
    queryset = Question.objects.none()
    filter_backends = (OrderingFilter,)
    ordering_fields = ('id', 'position')
    ordering = ('position', 'id')

    def get_queryset(self):
        return self.request.event.questions.prefetch_related('options').all()


class QuotaFilter(FilterSet):
    class Meta:
        model = Quota
        fields = ['subevent']


class QuotaViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = QuotaSerializer
    queryset = Quota.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter,)
    filter_class = QuotaFilter
    ordering_fields = ('id', 'size')
    ordering = ('id',)

    def get_queryset(self):
        return self.request.event.quotas.all()

    @detail_route(methods=['get'])
    def availability(self, request, *args, **kwargs):
        quota = self.get_object()

        avail = quota.availability()

        data = {
            'paid_orders': quota.count_paid_orders(),
            'pending_orders': quota.count_pending_orders(),
            'blocking_vouchers': quota.count_blocking_vouchers(),
            'cart_positions': quota.count_in_cart(),
            'waiting_list': quota.count_waiting_list_pending(),
            'available_number': avail[1],
            'available': avail[0] == Quota.AVAILABILITY_OK,
            'total_size': quota.size,
        }
        return Response(data)
