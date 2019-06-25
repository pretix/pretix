from rest_framework import filters, viewsets
from rest_framework.exceptions import PermissionDenied

from pretix.api.models import OAuthAccessToken
from pretix.api.serializers.organizer import (
    OrganizerSerializer, SeatingPlanSerializer,
)
from pretix.base.models import Organizer, SeatingPlan
from pretix.helpers.dicts import merge_dicts


class OrganizerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganizerSerializer
    queryset = Organizer.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'organizer'
    filter_backends = (filters.OrderingFilter,)
    ordering = ('slug',)
    ordering_fields = ('name', 'slug')

    def get_queryset(self):
        if self.request.user.is_authenticated:
            if self.request.user.has_active_staff_session(self.request.session.session_key):
                return Organizer.objects.all()
            elif isinstance(self.request.auth, OAuthAccessToken):
                return Organizer.objects.filter(
                    pk__in=self.request.user.teams.values_list('organizer', flat=True)
                ).filter(
                    pk__in=self.request.auth.organizers.values_list('pk', flat=True)
                )
            else:
                return Organizer.objects.filter(pk__in=self.request.user.teams.values_list('organizer', flat=True))
        elif hasattr(self.request.auth, 'organizer_id'):
            return Organizer.objects.filter(pk=self.request.auth.organizer_id)
        else:
            return Organizer.objects.filter(pk=self.request.auth.team.organizer_id)


class SeatingPlanViewSet(viewsets.ModelViewSet):
    serializer_class = SeatingPlanSerializer
    queryset = SeatingPlan.objects.none()
    permission = 'can_change_organizer_settings'
    write_permission = 'can_change_organizer_settings'

    def get_queryset(self):
        return self.request.organizer.seating_plans.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    def perform_create(self, serializer):
        inst = serializer.save(organizer=self.request.organizer)
        self.request.organizer.log_action(
            'pretix.seatingplan.added',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': inst.pk})
        )

    def perform_update(self, serializer):
        if serializer.instance.events.exists() or serializer.instance.subevents.exists():
            raise PermissionDenied('This plan can not be changed while it is in use for an event.')
        inst = serializer.save(organizer=self.request.organizer)
        self.request.organizer.log_action(
            'pretix.seatingplan.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': serializer.instance.pk})
        )
        return inst

    def perform_destroy(self, instance):
        if instance.events.exists() or instance.subevents.exists():
            raise PermissionDenied('This plan can not be deleted while it is in use for an event.')
        instance.log_action(
            'pretix.seatingplan.deleted',
            user=self.request.user,
            auth=self.request.auth,
            data={'id': instance.pk}
        )
        instance.delete()
