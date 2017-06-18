from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter

from pretix.api.serializers.item import (
    ItemCategorySerializer, ItemSerializer, QuestionSerializer,
    QuotaSerializer,
)
from pretix.base.models import Item, ItemCategory, Question, Quota


class ItemFilter(FilterSet):
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
        return self.request.event.items.prefetch_related('variations', 'addons').all()


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


class QuotaViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = QuotaSerializer
    queryset = Quota.objects.none()
    filter_backends = (OrderingFilter,)
    ordering_fields = ('id', 'size')
    ordering = ('id',)

    def get_queryset(self):
        return self.request.event.quotas.all()
