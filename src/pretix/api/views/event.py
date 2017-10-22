from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import filters, viewsets
from rest_framework.exceptions import PermissionDenied

from pretix.api.serializers.event import (
    EventSerializer, SubEventSerializer, TaxRuleSerializer,
)
from pretix.base.models import Event, ItemCategory, TaxRule
from pretix.base.models.event import SubEvent
from pretix.base.models.organizer import TeamAPIToken


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSerializer
    queryset = Event.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'event'

    def get_queryset(self):
        return self.request.organizer.events.prefetch_related('meta_values', 'meta_values__property')


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


class TaxRuleViewSet(viewsets.ModelViewSet):
    serializer_class = TaxRuleSerializer
    queryset = TaxRule.objects.none()
    write_permission = 'can_change_event_settings'

    def get_queryset(self):
        return self.request.event.tax_rules.all()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        serializer.instance.log_action(
            'pretix.event.taxrule.changed',
            user=self.request.user,
            api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
            data=self.request.data
        )

    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.taxrule.added',
            user=self.request.user,
            api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
            data=self.request.data
        )

    def perform_destroy(self, instance):
        if not instance.allow_delete():
            raise PermissionDenied('This tax rule can not be deleted as it is currently in use.')

        instance.log_action(
            'pretix.event.taxrule.deleted',
            user=self.request.user,
            api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
        )
        super().perform_destroy(instance)
