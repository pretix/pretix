import django_filters
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter

from pretix.api.serializers.waitinglist import WaitingListSerializer
from pretix.base.models import WaitingListEntry


class WaitingListFilter(FilterSet):
    has_voucher = django_filters.rest_framework.BooleanFilter(method='has_voucher_qs')

    def has_voucher_qs(self, queryset, name, value):
        return queryset.filter(voucher__isnull=not value)

    class Meta:
        model = WaitingListEntry
        fields = ['item', 'variation', 'email', 'locale', 'has_voucher', 'subevent']


class WaitingListViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WaitingListSerializer
    queryset = WaitingListEntry.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering = ('created',)
    ordering_fields = ('id', 'created', 'email', 'item')
    filter_class = WaitingListFilter
    permission = 'can_view_orders'

    def get_queryset(self):
        return self.request.event.waitinglistentries.all()
