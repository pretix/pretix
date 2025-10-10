#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
from rest_framework import serializers

from pretix.api.serializers import SalesChannelMigrationMixin
from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import Discount, SalesChannel


class DiscountSerializer(SalesChannelMigrationMixin, I18nAwareModelSerializer):
    limit_sales_channels = serializers.SlugRelatedField(
        slug_field="identifier",
        queryset=SalesChannel.objects.none(),
        required=False,
        allow_empty=True,
        many=True,
    )

    class Meta:
        model = Discount
        fields = ('id', 'active', 'internal_name', 'position', 'all_sales_channels', 'limit_sales_channels',
                  'available_from', 'available_until', 'subevent_mode', 'subevent_date_from', 'subevent_date_until',
                  'condition_all_products', 'condition_limit_products', 'condition_apply_to_addons',
                  'condition_min_count', 'condition_min_value', 'benefit_discount_matching_percent',
                  'benefit_only_apply_to_cheapest_n_matches', 'benefit_same_products', 'benefit_limit_products',
                  'benefit_apply_to_addons', 'benefit_ignore_voucher_discounted',
                  'condition_ignore_voucher_discounted')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['condition_limit_products'].queryset = self.context['event'].items.all()
        self.fields['benefit_limit_products'].queryset = self.context['event'].items.all()
        self.fields['limit_sales_channels'].child_relation.queryset = self.context['event'].organizer.sales_channels.all()

    def validate(self, data):
        data = super().validate(data)

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        Discount.validate_config(full_data)

        return data
