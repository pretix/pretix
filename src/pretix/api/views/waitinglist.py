from rest_framework import filters, viewsets

from pretix.api.filters.ordering import ExplicitOrderingFilter
from pretix.api.serializers.waitinglist import WaitingListSerializer
from pretix.base.models import WaitingListEntry


class WaitingListFilter(filters.FilterSet):
    class Meta:
        model = WaitingListEntry
        fields = ['item', 'variation', 'email', 'locale']


class WaitingListViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WaitingListSerializer
    queryset = WaitingListEntry.objects.none()
    filter_backends = (filters.DjangoFilterBackend, ExplicitOrderingFilter)
    ordering = ('created',)
    ordering_fields = ('id', 'created', 'email', 'item')
    filter_class = WaitingListFilter
    permission = 'can_view_orders'

    def get_queryset(self):
        return self.request.event.waitinglistentries.all()
