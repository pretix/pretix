import django_filters
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import filters, viewsets
from rest_framework.exceptions import PermissionDenied

from pretix.api.auth.permission import EventCRUDPermission
from pretix.api.serializers.event import (
    CloneEventSerializer, EventSerializer, SubEventSerializer,
    TaxRuleSerializer,
)
from pretix.api.views import ConditionalListView
from pretix.base.models import (
    CartPosition, Device, Event, ItemCategory, TaxRule, TeamAPIToken,
)
from pretix.base.models.event import SubEvent
from pretix.helpers.dicts import merge_dicts


class EventFilter(FilterSet):
    is_past = django_filters.rest_framework.BooleanFilter(method='is_past_qs')
    is_future = django_filters.rest_framework.BooleanFilter(method='is_future_qs')
    ends_after = django_filters.rest_framework.IsoDateTimeFilter(method='ends_after_qs')

    class Meta:
        model = Event
        fields = ['is_public', 'live', 'has_subevents']

    def ends_after_qs(self, queryset, name, value):
        expr = (
            Q(has_subevents=False) &
            Q(
                Q(Q(date_to__isnull=True) & Q(date_from__gte=value))
                | Q(Q(date_to__isnull=False) & Q(date_to__gte=value))
            )
        )
        return queryset.filter(expr)

    def is_past_qs(self, queryset, name, value):
        expr = (
            Q(has_subevents=False) &
            Q(
                Q(Q(date_to__isnull=True) & Q(date_from__lt=now()))
                | Q(Q(date_to__isnull=False) & Q(date_to__lt=now()))
            )
        )
        if value:
            return queryset.filter(expr)
        else:
            return queryset.exclude(expr)

    def is_future_qs(self, queryset, name, value):
        expr = (
            Q(has_subevents=False) &
            Q(
                Q(Q(date_to__isnull=True) & Q(date_from__gte=now()))
                | Q(Q(date_to__isnull=False) & Q(date_to__gte=now()))
            )
        )
        if value:
            return queryset.filter(expr)
        else:
            return queryset.exclude(expr)


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    queryset = Event.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'event'
    permission_classes = (EventCRUDPermission,)
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter)
    filterset_class = EventFilter

    def get_queryset(self):
        if isinstance(self.request.auth, (TeamAPIToken, Device)):
            qs = self.request.auth.get_events_with_any_permission()
        elif self.request.user.is_authenticated:
            qs = self.request.user.get_events_with_any_permission(self.request).filter(
                organizer=self.request.organizer
            )

        return qs.prefetch_related(
            'meta_values', 'meta_values__property'
        )

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
                auth=self.request.auth,
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
                    auth=self.request.auth,
                    data={'plugin': module}
                )

        other_keys = {k: v for k, v in serializer.validated_data.items() if k not in ['plugins', 'live']}
        if other_keys:
            serializer.instance.log_action(
                'pretix.event.changed',
                user=self.request.user,
                auth=self.request.auth,
                data=self.request.data
            )

    def perform_create(self, serializer):
        serializer.save(organizer=self.request.organizer)
        serializer.instance.log_action(
            'pretix.event.added',
            user=self.request.user,
            auth=self.request.auth,
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
            auth=self.request.auth,
            data=self.request.data
        )


class SubEventFilter(FilterSet):
    is_past = django_filters.rest_framework.BooleanFilter(method='is_past_qs')
    is_future = django_filters.rest_framework.BooleanFilter(method='is_future_qs')
    ends_after = django_filters.rest_framework.IsoDateTimeFilter(method='ends_after_qs')

    class Meta:
        model = SubEvent
        fields = ['active', 'event__live']

    def ends_after_qs(self, queryset, name, value):
        expr = Q(
            Q(Q(date_to__isnull=True) & Q(date_from__gte=value))
            | Q(Q(date_to__isnull=False) & Q(date_to__gte=value))
        )
        return queryset.filter(expr)

    def is_past_qs(self, queryset, name, value):
        expr = Q(
            Q(Q(date_to__isnull=True) & Q(date_from__lt=now()))
            | Q(Q(date_to__isnull=False) & Q(date_to__lt=now()))
        )
        if value:
            return queryset.filter(expr)
        else:
            return queryset.exclude(expr)

    def is_future_qs(self, queryset, name, value):
        expr = Q(
            Q(Q(date_to__isnull=True) & Q(date_from__gte=now()))
            | Q(Q(date_to__isnull=False) & Q(date_to__gte=now()))
        )
        if value:
            return queryset.filter(expr)
        else:
            return queryset.exclude(expr)


class SubEventViewSet(ConditionalListView, viewsets.ModelViewSet):
    serializer_class = SubEventSerializer
    queryset = ItemCategory.objects.none()
    write_permission = 'can_change_event_settings'
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter)
    filterset_class = SubEventFilter

    def get_queryset(self):
        if getattr(self.request, 'event', None):
            qs = self.request.event.subevents
        elif isinstance(self.request.auth, (TeamAPIToken, Device)):
            qs = SubEvent.objects.filter(
                event__organizer=self.request.organizer,
                event__in=self.request.auth.get_events_with_any_permission()
            )
        elif self.request.user.is_authenticated:
            qs = SubEvent.objects.filter(
                event__organizer=self.request.organizer,
                event__in=self.request.user.get_events_with_any_permission()
            )
        return qs.prefetch_related(
            'subeventitem_set', 'subeventitemvariation_set'
        )

    def perform_update(self, serializer):
        super().perform_update(serializer)

        serializer.instance.log_action(
            'pretix.subevent.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.subevent.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def perform_destroy(self, instance):
        if not instance.allow_delete():
            raise PermissionDenied('The sub-event can not be deleted as it has already been used in orders. Please set'
                                   ' \'active\' to false instead to hide it from users.')
        try:
            with transaction.atomic():
                instance.log_action(
                    'pretix.subevent.deleted',
                    user=self.request.user,
                    auth=self.request.auth,
                    data=self.request.data
                )
                CartPosition.objects.filter(addon_to__subevent=instance).delete()
                instance.cartposition_set.all().delete()
                super().perform_destroy(instance)
        except ProtectedError:
            raise PermissionDenied('The sub-event could not be deleted as some constraints (e.g. data created by '
                                   'plug-ins) do not allow it.')


class TaxRuleViewSet(ConditionalListView, viewsets.ModelViewSet):
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
            auth=self.request.auth,
            data=self.request.data
        )

    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.taxrule.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def perform_destroy(self, instance):
        if not instance.allow_delete():
            raise PermissionDenied('This tax rule can not be deleted as it is currently in use.')

        instance.log_action(
            'pretix.event.taxrule.deleted',
            user=self.request.user,
            auth=self.request.auth,
        )
        super().perform_destroy(instance)
