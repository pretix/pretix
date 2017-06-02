from requests import Response
from rest_framework import viewsets
from rest_framework.decorators import detail_route

from pretix.api.serializers.organizer import OrganizerSerializer
from pretix.base.models import Organizer


class OrganizerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganizerSerializer
    queryset = Organizer.objects.none()
    lookup_field = 'slug'

    def get_queryset(self):
        if self.request.user.is_authenticated():
            if self.request.user.is_superuser:
                return Organizer.objects.all()
            else:
                return Organizer.objects.filter(pk__in=self.request.user.teams.values_list('organizer', flat=True))
        else:
            return Organizer.objects.filter(pk=self.request.auth.team.organizer_id)

    @detail_route(methods=['get'])
    def events(self, request, *args, **kwargs):
        queryset = self.get_object().events.all()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
