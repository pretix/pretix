from rest_framework import viewsets

from pretix.api.serializers.organizer import OrganizerSerializer
from pretix.base.models import Organizer


class OrganizerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganizerSerializer
    queryset = Organizer.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'organizer'

    def get_queryset(self):
        if self.request.user.is_authenticated():
            if self.request.user.is_superuser:
                return Organizer.objects.all()
            else:
                return Organizer.objects.filter(pk__in=self.request.user.teams.values_list('organizer', flat=True))
        else:
            return Organizer.objects.filter(pk=self.request.auth.team.organizer_id)
