from rest_framework import viewsets

from pretix.api.serializers.event import EventSerializer
from pretix.base.models import Event


class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
