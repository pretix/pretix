from rest_framework import viewsets

from pretix.api.serializers.event import EventSerializer
from pretix.base.models import Event


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSerializer
    queryset = Event.objects.none()
    lookup_field = 'slug'

    def get_queryset(self):
        if self.request.user.is_authenticated():
            return self.request.user.get_events_with_any_permission()
        else:
            return self.request.auth.get_events_with_any_permission()
