from django.db import transaction
from django.db.models import ProtectedError
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import filters, viewsets
from rest_framework.exceptions import PermissionDenied

from pretix.api.auth.permission import EventCRUDPermission
from pretix.api.serializers.event import (
    EventSerializer, SubEventSerializer, TaxRuleSerializer,
)
from pretix.base.models import Event, ItemCategory, TaxRule
from pretix.base.models.event import SubEvent
from pretix.base.models.organizer import TeamAPIToken


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    queryset = Event.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'event'
    permission_classes = (EventCRUDPermission,)

    def get_queryset(self):
        return self.request.organizer.events.prefetch_related('meta_values', 'meta_values__property')

    def perform_update(self, serializer):
        super().perform_update(serializer)
        serializer.instance.log_action(
            'pretix.event.changed',
            user=self.request.user,
            api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
            data=self.request.data
        )

    def perform_create(self, serializer):
        serializer.save(organizer=self.request.organizer)
        serializer.instance.log_action(
            'pretix.event.added',
            user=self.request.user,
            api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
            data=self.request.data
        )

    def perform_destroy(self, instance):
        if not instance.allow_delete():
            raise PermissionDenied('The event can not be deleted as it already contains orders. Please set \'live\''
                                   ' to false to hide the event and take the shop offline instead.')
        try:
            with transaction.atomic():
                instance.organizer.log_action(
                    'pretix.event.deleted', user=self.request.user,
                    data={
                        'event_id': instance.pk,
                        'name': str(instance.name),
                        'logentries': list(instance.logentry_set.values_list('pk', flat=True))
                    }
                )
                instance.delete_sub_objects()
                super().perform_destroy(instance)
        except ProtectedError:
            raise PermissionDenied('The event could not be deleted as some constraints (e.g. data created by plug-ins) '
                                   'do not allow it.')


class CloneEventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    queryset = Event.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'event'
    http_method_names = ['post']
    write_permission = 'can_create_events'

    def perform_create(self, serializer):
        serializer.save(organizer=self.request.organizer)
        plugins = serializer.instance.plugins
        is_public = serializer.instance.is_public

        event = Event.objects.filter(slug=self.kwargs['event'], organizer=self.request.organizer.pk).first()
        serializer.instance.copy_data_from(event)

        if 'plugins' in serializer.initial_data:
            serializer.instance.plugins = plugins
        if 'is_public' in serializer.initial_data:
            serializer.instance.is_public = is_public
        serializer.instance.save()

        serializer.instance.log_action(
            'pretix.event.added',
            user=self.request.user,
            api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
            data=self.request.data
        )


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
