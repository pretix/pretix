from rest_framework import viewsets

from pretix.api.serializers.event import EventSerializer
from pretix.base.models import Event


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSerializer
    queryset = Event.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'event'

    def get_queryset(self):
        return self.request.organizer.events.all()
