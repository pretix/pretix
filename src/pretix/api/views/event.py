from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import filters, viewsets

from pretix.api.serializers.event import EventSerializer, SubEventSerializer
from pretix.base.models import Event, ItemCategory
from pretix.base.models.event import SubEvent


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSerializer
    queryset = Event.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'event'

    def get_queryset(self):
        return self.request.organizer.events.all()


class SubEventFilter(FilterSet):
    class Meta:
        model = SubEvent
        fields = ['active']


class SubEventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SubEventSerializer
    queryset = ItemCategory.objects.none()
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter)
    filter_class = SubEventFilter

    def get_queryset(self):
        return self.request.event.subevents.prefetch_related(
            'subeventitem_set', 'subeventitemvariation_set'
        )
