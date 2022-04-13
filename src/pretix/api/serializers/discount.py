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

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import Discount


class DiscountSerializer(I18nAwareModelSerializer):

    class Meta:
        model = Discount
        fields = ('id', 'active', 'internal_name', 'position', 'sales_channels', 'available_from',
                  'available_until', 'subevent_mode', 'condition_all_products', 'condition_limit_products',
                  'condition_apply_to_addons', 'condition_min_count', 'condition_min_value',
                  'benefit_discount_matching_percent', 'benefit_only_apply_to_cheapest_n_matches',
                  'condition_ignore_voucher_discounted')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['condition_limit_products'].queryset = self.context['event'].items.all()

    def validate(self, data):
        data = super().validate(data)

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        Discount.validate_config(full_data)

        return data
