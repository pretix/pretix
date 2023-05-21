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
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import WaitingListEntry


class WaitingListSerializer(I18nAwareModelSerializer):

    class Meta:
        model = WaitingListEntry
        fields = ('id', 'created', 'name', 'name_parts', 'email', 'phone', 'voucher', 'item', 'variation', 'locale', 'subevent', 'priority')
        read_only_fields = ('id', 'created', 'voucher')

    def validate(self, data):
        data = super().validate(data)
        event = self.context['event']

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        WaitingListEntry.clean_duplicate(event, full_data.get('email'), full_data.get('item'), full_data.get('variation'),
                                         full_data.get('subevent'), self.instance.pk if self.instance else None)
        WaitingListEntry.clean_itemvar(event, full_data.get('item'), full_data.get('variation'))
        WaitingListEntry.clean_subevent(event, full_data.get('subevent'))

        if 'item' in data or 'variation' in data:
            availability = (
                full_data.get('variation').check_quotas(count_waitinglist=True, subevent=full_data.get('subevent'))
                if full_data.get('variation')
                else full_data.get('item').check_quotas(count_waitinglist=True, subevent=full_data.get('subevent'))
            )
            if availability[0] == 100:
                raise ValidationError("This product is currently available.")

        if data.get('name') and data.get('name_parts'):
            raise ValidationError(
                {'name': ['Do not specify name if you specified name_parts.']}
            )
        if data.get('name_parts') and '_scheme' not in data.get('name_parts'):
            data['name_parts']['_scheme'] = event.settings.name_scheme

        return data
