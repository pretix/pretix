#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Ture Gjørup
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import django_filters
from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch, ProtectedError, Q
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from django_scopes import scopes_disabled
from rest_framework import serializers, views, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from pretix.api.auth.permission import EventCRUDPermission
from pretix.api.pagination import TotalOrderingFilter
from pretix.api.serializers.event import (
    CloneEventSerializer, DeviceEventSettingsSerializer, EventSerializer,
    EventSettingsSerializer, ItemMetaPropertiesSerializer, SubEventSerializer,
    TaxRuleSerializer,
)
from pretix.api.views import ConditionalListView
from pretix.base.models import (
    CartPosition, Device, Event, ItemMetaProperty, SeatCategoryMapping,
    TaxRule, TeamAPIToken,
)
from pretix.base.models.event import SubEvent
from pretix.base.services.quotas import QuotaAvailability
from pretix.base.settings import SETTINGS_AFFECTING_CSS
from pretix.helpers.dicts import merge_dicts
from pretix.helpers.i18n import i18ncomp
from pretix.presale.style import regenerate_css
from pretix.presale.views.organizer import filter_qs_by_attr

with scopes_disabled():
    class EventFilter(FilterSet):

        is_past = django_filters.rest_framework.BooleanFilter(method='is_past_qs')
        is_future = django_filters.rest_framework.BooleanFilter(method='is_future_qs')
        ends_after = django_filters.rest_framework.IsoDateTimeFilter(method='ends_after_qs')
        sales_channel = django_filters.rest_framework.CharFilter(method='sales_channel_qs')
        search = django_filters.rest_framework.CharFilter(method='search_qs')
        date_from = django_filters.rest_framework.IsoDateTimeFromToRangeFilter()
        date_to = django_filters.rest_framework.IsoDateTimeFromToRangeFilter()

        class Meta:
            model = Event
            fields = ['is_public', 'live', 'has_subevents', 'testmode']

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

        def sales_channel_qs(self, queryset, name, value):
            return queryset.filter(sales_channels__contains=value)

        def search_qs(self, queryset, name, value):
            return queryset.filter(
                Q(name__icontains=i18ncomp(value))
                | Q(slug__icontains=value)
                | Q(location__icontains=i18ncomp(value))
            )


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    queryset = Event.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'event'
    lookup_value_regex = '[^/]+'
    permission_classes = (EventCRUDPermission,)
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter)
    ordering = ('slug',)
    ordering_fields = ('date_from', 'slug')
    filterset_class = EventFilter

    def get_copy_from_queryset(self):
        if isinstance(self.request.auth, (TeamAPIToken, Device)):
            return self.request.auth.get_events_with_any_permission()
        elif self.request.user.is_authenticated:
            return self.request.user.get_events_with_any_permission(self.request)
        return Event.objects.none()

    def get_queryset(self):
        if isinstance(self.request.auth, (TeamAPIToken, Device)):
            qs = self.request.auth.get_events_with_any_permission()
        elif self.request.user.is_authenticated:
            qs = self.request.user.get_events_with_any_permission(self.request).filter(
                organizer=self.request.organizer
            )

        qs = filter_qs_by_attr(qs, self.request)

        if 'with_availability_for' in self.request.GET:
            qs = Event.annotated(qs, channel=self.request.GET.get('with_availability_for'))

        return qs.prefetch_related(
            'organizer',
            'meta_values',
            'meta_values__property',
            'item_meta_properties',
            Prefetch(
                'seat_category_mappings',
                to_attr='_seat_category_mappings',
                queryset=SeatCategoryMapping.objects.filter(subevent=None)
            ),
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)

        if 'with_availability_for' in self.request.GET:
            quotas_to_compute = []
            qcache = {}
            for se in page:
                se._quota_cache = qcache
                quotas_to_compute += se.active_quotas

            if quotas_to_compute:
                qa = QuotaAvailability()
                qa.queue(*quotas_to_compute)
                qa.compute(allow_cache=True)
                qcache.update(qa.results)

        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

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
        copy_from = None
        if 'clone_from' in self.request.GET:
            src = self.request.GET.get('clone_from')
            try:
                if '/' in src:
                    copy_from = self.get_copy_from_queryset().get(
                        organizer__slug=src.split('/')[0],
                        slug=src.split('/')[1]
                    )
                else:
                    copy_from = self.get_copy_from_queryset().get(
                        organizer=self.request.organizer,
                        slug=src
                    )
            except Event.DoesNotExist:
                raise ValidationError('Event to copy from was not found')

        # Ensure that .installed() is only called when we NOT clone
        plugins = serializer.validated_data.pop('plugins', None)
        serializer.validated_data['plugins'] = None

        new_event = serializer.save(organizer=self.request.organizer)

        if copy_from:
            new_event.copy_data_from(copy_from)

            if plugins is not None:
                new_event.set_active_plugins(plugins)
            if 'is_public' in serializer.validated_data:
                new_event.is_public = serializer.validated_data['is_public']
            if 'testmode' in serializer.validated_data:
                new_event.testmode = serializer.validated_data['testmode']
            if 'sales_channels' in serializer.validated_data:
                new_event.sales_channels = serializer.validated_data['sales_channels']
            if 'has_subevents' in serializer.validated_data:
                new_event.has_subevents = serializer.validated_data['has_subevents']
            if 'date_admission' in serializer.validated_data:
                new_event.date_admission = serializer.validated_data['date_admission']
            new_event.save()
            if 'timezone' in serializer.validated_data:
                new_event.settings.timezone = serializer.validated_data['timezone']
        else:
            serializer.instance.set_defaults()

            new_event.set_active_plugins(plugins if plugins is not None else settings.PRETIX_PLUGINS_DEFAULT.split(','))
            new_event.save(update_fields=['plugins'])

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


with scopes_disabled():
    class SubEventFilter(FilterSet):
        is_past = django_filters.rest_framework.BooleanFilter(method='is_past_qs')
        is_future = django_filters.rest_framework.BooleanFilter(method='is_future_qs')
        ends_after = django_filters.rest_framework.IsoDateTimeFilter(method='ends_after_qs')
        modified_since = django_filters.IsoDateTimeFilter(field_name='last_modified', lookup_expr='gte')
        sales_channel = django_filters.rest_framework.CharFilter(method='sales_channel_qs')
        search = django_filters.rest_framework.CharFilter(method='search_qs')
        date_from = django_filters.rest_framework.IsoDateTimeFromToRangeFilter()
        date_to = django_filters.rest_framework.IsoDateTimeFromToRangeFilter()

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

        def sales_channel_qs(self, queryset, name, value):
            return queryset.filter(event__sales_channels__contains=value)

        def search_qs(self, queryset, name, value):
            return queryset.filter(
                Q(name__icontains=i18ncomp(value))
                | Q(location__icontains=i18ncomp(value))
            )


class SubEventViewSet(ConditionalListView, viewsets.ModelViewSet):
    serializer_class = SubEventSerializer
    queryset = SubEvent.objects.none()
    write_permission = 'can_change_event_settings'
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter)
    filterset_class = SubEventFilter
    ordering = ('date_from',)
    ordering_fields = ('id', 'date_from', 'last_modified')

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

        qs = filter_qs_by_attr(qs, self.request)

        if 'with_availability_for' in self.request.GET:
            qs = SubEvent.annotated(qs, channel=self.request.GET.get('with_availability_for'))

        return qs.prefetch_related(
            'event',
            'subeventitem_set',
            'subeventitemvariation_set',
            'meta_values',
            Prefetch(
                'seat_category_mappings',
                to_attr='_seat_category_mappings',
            ),
        )

    def list(self, request, **kwargs):
        date = serializers.DateTimeField().to_representation(now())
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)

        if 'with_availability_for' in self.request.GET:
            quotas_to_compute = []
            qcache = {}
            for se in page:
                se._quota_cache = qcache
                quotas_to_compute += se.active_quotas

            if quotas_to_compute:
                qa = QuotaAvailability()
                qa.queue(*quotas_to_compute)
                qa.compute(allow_cache=True)
                qcache.update(qa.results)

        serializer = self.get_serializer(page, many=True)
        resp = self.get_paginated_response(serializer.data)
        resp['X-Page-Generated'] = date
        return resp

    def perform_update(self, serializer):
        original_data = self.get_serializer(instance=serializer.instance).data
        super().perform_update(serializer)

        if serializer.data == original_data:
            # Performance optimization: If nothing was changed, we do not need to save or log anything.
            # This costs us a few cycles on save, but avoids thousands of lines in our log.
            return

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


class ItemMetaPropertiesViewSet(viewsets.ModelViewSet):
    serializer_class = ItemMetaPropertiesSerializer
    queryset = ItemMetaProperty.objects.none()
    write_permission = 'can_change_event_settings'

    def get_queryset(self):
        qs = self.request.event.item_meta_properties.all()
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        ctx['event'] = self.request.event
        return ctx

    @transaction.atomic()
    def perform_destroy(self, instance):
        instance.log_action(
            'pretix.event.item_meta_property.deleted',
            user=self.request.user,
            auth=self.request.auth,
            data={'id': instance.pk}
        )
        instance.delete()

    @transaction.atomic()
    def perform_create(self, serializer):
        inst = serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.item_meta_property.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )
        return inst

    @transaction.atomic()
    def perform_update(self, serializer):
        inst = serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.item_meta_property.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )
        return inst


class EventSettingsView(views.APIView):
    permission = None
    write_permission = 'can_change_event_settings'

    def get(self, request, *args, **kwargs):
        if isinstance(request.auth, Device):
            s = DeviceEventSettingsSerializer(instance=request.event.settings, event=request.event, context={
                'request': request
            })
        elif 'can_change_event_settings' in request.eventpermset:
            s = EventSettingsSerializer(instance=request.event.settings, event=request.event, context={
                'request': request
            })
        else:
            raise PermissionDenied()
        if 'explain' in request.GET:
            return Response({
                fname: {
                    'value': s.data[fname],
                    'label': getattr(field, '_label', fname),
                    'help_text': getattr(field, '_help_text', None),
                    'readonly': fname in s.readonly_fields,
                } for fname, field in s.fields.items()
            })
        return Response(s.data)

    def patch(self, request, *wargs, **kwargs):
        s = EventSettingsSerializer(instance=request.event.settings, data=request.data, partial=True,
                                    event=request.event, context={'request': request})
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            s.save()
            self.request.event.log_action(
                'pretix.event.settings', user=self.request.user, auth=self.request.auth, data={
                    k: v for k, v in s.validated_data.items()
                }
            )
        if any(p in s.changed_data for p in SETTINGS_AFFECTING_CSS):
            regenerate_css.apply_async(args=(request.event.pk,))
        s = EventSettingsSerializer(
            instance=request.event.settings, event=request.event, context={
                'request': request
            })
        return Response(s.data)
