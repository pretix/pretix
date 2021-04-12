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
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.event import SubEventSerializer
from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.channels import get_all_sales_channels
from pretix.base.models import CheckinList


class CheckinListSerializer(I18nAwareModelSerializer):
    checkin_count = serializers.IntegerField(read_only=True)
    position_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = CheckinList
        fields = ('id', 'name', 'all_products', 'limit_products', 'subevent', 'checkin_count', 'position_count',
                  'include_pending', 'auto_checkin_sales_channels', 'allow_multiple_entries', 'allow_entry_after_exit',
                  'rules', 'exit_all_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'subevent' in self.context['request'].query_params.getlist('expand'):
            self.fields['subevent'] = SubEventSerializer(read_only=True)

        for exclude_field in self.context['request'].query_params.getlist('exclude'):
            p = exclude_field.split('.')
            if p[0] in self.fields:
                if len(p) == 1:
                    del self.fields[p[0]]
                elif len(p) == 2:
                    self.fields[p[0]].child.fields.pop(p[1])

    def validate(self, data):
        data = super().validate(data)
        event = self.context['event']

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        for item in full_data.get('limit_products'):
            if event != item.event:
                raise ValidationError(_('One or more items do not belong to this event.'))

        if event.has_subevents:
            if full_data.get('subevent') and event != full_data.get('subevent').event:
                raise ValidationError(_('The subevent does not belong to this event.'))
        else:
            if full_data.get('subevent'):
                raise ValidationError(_('The subevent does not belong to this event.'))

        for channel in full_data.get('auto_checkin_sales_channels') or []:
            if channel not in get_all_sales_channels():
                raise ValidationError(_('Unknown sales channel.'))

        CheckinList.validate_rules(data.get('rules'))

        return data
