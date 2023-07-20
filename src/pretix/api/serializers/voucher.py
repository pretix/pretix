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
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import Seat, Voucher


class VoucherListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        codes = set()
        seats = set()
        errs = []
        err = False
        for voucher_data in validated_data:
            if voucher_data.get('seat') and (voucher_data.get('seat'), voucher_data.get('subevent')) in seats:
                err = True
                errs.append({'code': ['Duplicate seat ID in request.']})
                continue
            else:
                seats.add((voucher_data.get('seat'), voucher_data.get('subevent')))

            if voucher_data['code'] in codes:
                err = True
                errs.append({'code': ['Duplicate voucher code in request.']})
            else:
                codes.add(voucher_data['code'])
                errs.append({})
        if err:
            raise ValidationError(errs)
        return super().create(validated_data)


class SeatGuidField(serializers.CharField):
    def to_representation(self, val: Seat):
        return val.seat_guid


class VoucherSerializer(I18nAwareModelSerializer):
    seat = SeatGuidField(allow_null=True, required=False)

    class Meta:
        model = Voucher
        fields = ('id', 'code', 'max_usages', 'redeemed', 'min_usages', 'valid_until', 'block_quota',
                  'allow_ignore_quota', 'price_mode', 'value', 'item', 'variation', 'quota',
                  'tag', 'comment', 'subevent', 'show_hidden_items', 'seat', 'all_addons_included',
                  'all_bundles_included')
        read_only_fields = ('id', 'redeemed')
        list_serializer_class = VoucherListSerializer

    def validate(self, data):
        data = super().validate(data)

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        Voucher.clean_item_properties(
            full_data, self.context.get('event'),
            full_data.get('quota'), full_data.get('item'), full_data.get('variation'),
            block_quota=full_data.get('block_quota')
        )
        Voucher.clean_subevent(
            full_data, self.context.get('event')
        )
        Voucher.clean_max_usages(full_data, self.instance.redeemed if self.instance else 0)
        check_quota = Voucher.clean_quota_needs_checking(
            full_data, self.instance,
            item_changed=self.instance and (
                full_data.get('item') != self.instance.item or
                full_data.get('variation') != self.instance.variation or
                full_data.get('quota') != self.instance.quota
            ),
            creating=not self.instance
        )
        if check_quota:
            Voucher.clean_quota_check(
                full_data, 1, self.instance, self.context.get('event'),
                full_data.get('quota'), full_data.get('item'), full_data.get('variation')
            )
        Voucher.clean_voucher_code(full_data, self.context.get('event'), self.instance.pk if self.instance else None)

        if full_data.get('seat'):
            data['seat'] = Voucher.clean_seat_id(
                full_data, full_data.get('item'), full_data.get('quota'), self.context.get('event'),
                self.instance.pk if self.instance else None
            )

        return data
