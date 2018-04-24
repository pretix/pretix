from django.db import transaction
from django.db.models import ProtectedError
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import filters, viewsets
from rest_framework.exceptions import PermissionDenied

from pretix.api.auth.permission import EventCRUDPermission
from pretix.api.serializers.event import (
    CloneEventSerializer, EventSerializer, SubEventSerializer,
    TaxRuleSerializer,
)
from pretix.base.models import Event, ItemCategory, TaxRule
from pretix.base.models.event import SubEvent
from pretix.base.models.organizer import TeamAPIToken
from pretix.helpers.dicts import merge_dicts


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    queryset = Event.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'event'
    permission_classes = (EventCRUDPermission,)

    def get_queryset(self):
        return self.request.organizer.events.prefetch_related('meta_values', 'meta_values__property')

    def perform_update(self, serializer):
        current_live_value = serializer.instance.live
        updated_live_value = serializer.validated_data.get('live', None)
        current_plugins_value = serializer.instance.get_plugins()
        updated_plugins_value = serializer.validated_data.get('plugins', None)

        super().perform_update(serializer)

        if updated_live_value is not None and updated_live_value != current_live_value:
            log_action = 'pretix.event.live.activated' if updated_live_value else 'pretix.event.live.deactivated'
            serializer.instance.log_action(
                log_action,
                user=self.request.user,
                api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
                data=self.request.data
            )

        if updated_plugins_value is not None and set(updated_plugins_value) != set(current_plugins_value):
            enabled = {m: 'enabled' for m in updated_plugins_value if m not in current_plugins_value}
            disabled = {m: 'disabled' for m in current_plugins_value if m not in updated_plugins_value}
            changed = merge_dicts(enabled, disabled)

            for module, action in changed.items():
                serializer.instance.log_action(
                    'pretix.event.plugins.' + action,
                    user=self.request.user,
                    api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
                    data={'plugin': module}
                )

        other_keys = {k: v for k, v in serializer.validated_data.items() if k not in ['plugins', 'live']}
        if other_keys:
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
    serializer_class = CloneEventSerializer
    queryset = Event.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'event'
    http_method_names = ['post']
    write_permission = 'can_create_events'

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.kwargs['event']
        ctx['organizer'] = self.request.organizer
        return ctx

    def perform_create(self, serializer):
        serializer.save(organizer=self.request.organizer)

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
