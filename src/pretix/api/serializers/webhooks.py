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
from rest_framework import serializers

from pretix.api.models import WebHook
from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.webhooks import get_all_webhook_events
from pretix.base.models import Event


class EventRelatedField(serializers.SlugRelatedField):
    def get_queryset(self):
        return self.context['organizer'].events.all()


class ActionTypesField(serializers.Field):
    def to_representation(self, instance: WebHook):
        return instance.action_types

    def to_internal_value(self, data):
        types = get_all_webhook_events()
        for d in data:
            if d not in types:
                raise ValidationError('Invalid action type "%s".' % d)
        return {'action_types': data}


class WebHookSerializer(I18nAwareModelSerializer):
    limit_events = EventRelatedField(
        slug_field='slug',
        queryset=Event.objects.none(),
        many=True
    )
    action_types = ActionTypesField(source='*')

    class Meta:
        model = WebHook
        fields = ('id', 'enabled', 'target_url', 'all_events', 'limit_events', 'action_types', 'comment')

    def validate(self, data):
        data = super().validate(data)

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        for event in full_data.get('limit_events'):
            if self.context['organizer'] != event.organizer:
                raise ValidationError('One or more events do not belong to this organizer.')

        if full_data.get('limit_events') and full_data.get('all_events'):
            raise ValidationError('You can set either limit_events or all_events.')

        return data

    def create(self, validated_data):
        action_types = validated_data.pop('action_types')
        inst = super().create(validated_data)
        for l in action_types:
            inst.listeners.create(action_type=l)
        return inst

    def update(self, instance, validated_data):
        action_types = validated_data.pop('action_types', None)
        instance = super().update(instance, validated_data)
        if action_types is not None:
            current_listeners = set(instance.listeners.values_list('action_type', flat=True))
            new_listeners = set(action_types)
            for l in current_listeners - new_listeners:
                instance.listeners.filter(action_type=l).delete()
            for l in new_listeners - current_listeners:
                instance.listeners.create(action_type=l)
        return instance
