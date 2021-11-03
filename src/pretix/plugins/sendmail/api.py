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
from django.core.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from django_scopes import scopes_disabled
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.plugins.sendmail.models import Rule


class RuleSerializer(I18nAwareModelSerializer):
    class Meta:
        model = Rule
        fields = ['id', 'subject', 'template', 'all_products', 'limit_products', 'include_pending',
                  'send_date', 'send_offset_days', 'send_offset_time', 'date_is_absolute',
                  'offset_to_event_end', 'offset_is_after', 'send_to', 'enabled']
        read_only_fields = ['id']

    def validate(self, data):
        data = super().validate(data)

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        if full_data.get('date_is_absolute') is not False:
            if any([k in data for k in ['offset_to_event_end', 'offset_is_after']]):
                raise ValidationError('date_is_absolute and offset_* are mutually exclusive')
            if not full_data.get('send_date'):
                raise ValidationError('send_date is required for date_is_absolute=True')
        else:
            if not all([full_data.get(k) for k in ['send_offset_days', 'send_offset_time']]):
                raise ValidationError('send_offset_days and send_offset_time are required for date_is_absolute=False')

        if full_data.get('all_products') is False:
            if not full_data.get('limit_products'):
                raise ValidationError('limit_products is required when all_products=False')

        return full_data

    def save(self, **kwargs):
        return super().save(event=self.context['request'].event)


with scopes_disabled():
    class RuleFilter(FilterSet):
        class Meta:
            model = Rule
            fields = ['id', 'all_products', 'include_pending', 'date_is_absolute',
                      'offset_to_event_end', 'offset_is_after', 'send_to', 'enabled']


class RuleViewSet(viewsets.ModelViewSet):
    queryset = Rule.objects.none()
    serializer_class = RuleSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = RuleFilter
    ordering = ('id',)
    ordering_fields = ('id',)
    permission = 'can_change_event_settings'

    def get_queryset(self):
        return Rule.objects.filter(event=self.request.event)

    def perform_create(self, serializer):
        super().perform_create(serializer)
        serializer.instance.log_action(
            'pretix.plugins.sendmail.rule.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data

        )

    def perform_update(self, serializer):
        super().perform_update(serializer)
        serializer.instance.log_action(
            'pretix.plugins.sendmail.rule.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def perform_destroy(self, instance):
        instance.log_action(
            'pretix.plugins.sendmail.rule.deleted',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )
        super().perform_destroy(instance)
