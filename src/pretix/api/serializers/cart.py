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
import os
from datetime import timedelta

from django.core.files import File
from django.db.models import prefetch_related_objects
from django.utils.timezone import now
from django.utils.translation import gettext_lazy
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import (
    AnswerCreateSerializer, AnswerSerializer, InlineSeatSerializer,
)
from pretix.base.models import Seat, Voucher
from pretix.base.models.orders import CartPosition


class TaxIncludedField(serializers.Field):
    def to_representation(self, instance: CartPosition):
        return not instance.custom_price_input_is_net


class CartPositionSerializer(I18nAwareModelSerializer):
    answers = AnswerSerializer(many=True)
    seat = InlineSeatSerializer()
    includes_tax = TaxIncludedField(source='*')

    class Meta:
        model = CartPosition
        fields = ('id', 'cart_id', 'item', 'variation', 'price', 'attendee_name', 'attendee_name_parts',
                  'attendee_email', 'voucher', 'addon_to', 'subevent', 'datetime', 'expires', 'includes_tax',
                  'answers', 'seat', 'is_bundled')


class BaseCartPositionCreateSerializer(I18nAwareModelSerializer):
    answers = AnswerCreateSerializer(many=True, required=False)
    attendee_name = serializers.CharField(required=False, allow_null=True)
    includes_tax = serializers.BooleanField(required=False, allow_null=True)

    class Meta:
        model = CartPosition
        fields = ('item', 'variation', 'price', 'attendee_name', 'attendee_name_parts', 'attendee_email',
                  'subevent', 'includes_tax', 'answers')

    def validate_item(self, item):
        if item.event != self.context['event']:
            raise ValidationError(
                'The specified item does not belong to this event.'
            )
        if not item.active:
            raise ValidationError(
                'The specified item is not active.'
            )
        return item

    def validate_subevent(self, subevent):
        if self.context['event'].has_subevents:
            if not subevent:
                raise ValidationError(
                    'You need to set a subevent.'
                )
            if subevent.event != self.context['event']:
                raise ValidationError(
                    'The specified subevent does not belong to this event.'
                )
        elif subevent:
            raise ValidationError(
                'You cannot set a subevent for this event.'
            )
        return subevent

    def validate(self, data):
        if data.get('item'):
            if data.get('item').has_variations:
                if not data.get('variation'):
                    raise ValidationError('You should specify a variation for this item.')
                else:
                    if data.get('variation').item != data.get('item'):
                        raise ValidationError(
                            'The specified variation does not belong to the specified item.'
                        )
            elif data.get('variation'):
                raise ValidationError(
                    'You cannot specify a variation for this item.'
                )
        if data.get('attendee_name') and data.get('attendee_name_parts'):
            raise ValidationError(
                {'attendee_name': ['Do not specify attendee_name if you specified attendee_name_parts.']}
            )

        if not data.get('expires'):
            data['expires'] = now() + timedelta(
                minutes=self.context['event'].settings.get('reservation_time', as_type=int)
            )

        quotas_for_item_cache = self.context.get('quotas_for_item_cache', {})
        quotas_for_variation_cache = self.context.get('quotas_for_variation_cache', {})

        seated = data.get('item').seat_category_mappings.filter(subevent=data.get('subevent')).exists()
        if data.get('seat'):
            if not seated:
                raise ValidationError({'seat': ['The specified product does not allow to choose a seat.']})
            try:
                seat = self.context['event'].seats.get(seat_guid=data['seat'], subevent=data.get('subevent'))
            except Seat.DoesNotExist:
                raise ValidationError({'seat': ['The specified seat does not exist.']})
            except Seat.MultipleObjectsReturned:
                raise ValidationError({'seat': ['The specified seat ID is not unique.']})
            else:
                data['seat'] = seat
        elif seated:
            raise ValidationError({'seat': ['The specified product requires to choose a seat.']})

        if data.get('voucher'):
            try:
                voucher = self.context['event'].vouchers.get(code__iexact=data['voucher'])
            except Voucher.DoesNotExist:
                raise ValidationError({'voucher': ['The specified voucher does not exist.']})

            if voucher and not voucher.applies_to(data['item'], data.get('variation')):
                raise ValidationError({'voucher': ['The specified voucher is not valid for the given item and variation.']})

            if voucher and voucher.seat and voucher.seat != data.get('seat'):
                raise ValidationError({'voucher': ['The specified voucher is not valid for this seat.']})

            if voucher and voucher.subevent_id and (not data.get('subevent') or voucher.subevent_id != data['subevent'].pk):
                raise ValidationError({'voucher': ['The specified voucher is not valid for this subevent.']})

            if voucher.valid_until is not None and voucher.valid_until < now():
                raise ValidationError({'voucher': ['The specified voucher is expired.']})

            data['voucher'] = voucher

        if not data.get('voucher') or (not data['voucher'].allow_ignore_quota and not data['voucher'].block_quota):
            if data.get('variation'):
                if data['variation'].pk not in quotas_for_variation_cache:
                    quotas_for_variation_cache[data['variation'].pk] = data['variation'].quotas.filter(subevent=data.get('subevent'))
                data['_quotas'] = quotas_for_variation_cache[data['variation'].pk]
            else:
                if data['item'].pk not in quotas_for_item_cache:
                    quotas_for_item_cache[data['item'].pk] = data['item'].quotas.filter(subevent=data.get('subevent'))
                data['_quotas'] = quotas_for_item_cache[data['item'].pk]

            if len(data['_quotas']) == 0:
                raise ValidationError(
                    gettext_lazy('The product "{}" is not assigned to a quota.').format(
                        str(data.get('item'))
                    )
                )
        else:
            data['_quotas'] = []

        return data

    def create(self, validated_data):
        validated_data.pop('_quotas')
        answers_data = validated_data.pop('answers')

        attendee_name = validated_data.pop('attendee_name', '')
        if attendee_name and not validated_data.get('attendee_name_parts'):
            validated_data['attendee_name_parts'] = {
                '_legacy': attendee_name
            }

        # todo: does this make sense?
        validated_data['custom_price_input'] = validated_data['price']
        # todo: listed price, etc?
        # currently does not matter because there is no way to transform an API cart position into an order that keeps
        # prices, cart positions are just quota/voucher placeholders
        validated_data['custom_price_input_is_net'] = not validated_data.pop('includes_tax', True)
        cp = CartPosition.objects.create(event=self.context['event'], **validated_data)

        for answ_data in answers_data:
            options = answ_data.pop('options')
            if isinstance(answ_data['answer'], File):
                an = answ_data.pop('answer')
                answ = cp.answers.create(**answ_data, answer='')
                answ.file.save(os.path.basename(an.name), an, save=False)
                answ.answer = 'file://' + answ.file.name
                answ.save()
                an.close()
            else:
                answ = cp.answers.create(**answ_data)
                answ.options.add(*options)
        return cp


class CartPositionCreateSerializer(BaseCartPositionCreateSerializer):
    expires = serializers.DateTimeField(required=False)
    addons = BaseCartPositionCreateSerializer(many=True, required=False)
    bundled = BaseCartPositionCreateSerializer(many=True, required=False)
    seat = serializers.CharField(required=False, allow_null=True)
    sales_channel = serializers.CharField(required=False, default='sales_channel')
    voucher = serializers.CharField(required=False, allow_null=True)

    class Meta:
        model = CartPosition
        fields = BaseCartPositionCreateSerializer.Meta.fields + (
            'cart_id', 'expires', 'addons', 'bundled', 'seat', 'sales_channel', 'voucher'
        )

    def validate_cart_id(self, cid):
        if cid and not cid.endswith('@api'):
            raise ValidationError('Cart ID should end in @api or be empty.')
        return cid

    def create(self, validated_data):
        validated_data.pop('sales_channel')
        addons_data = validated_data.pop('addons', None)
        bundled_data = validated_data.pop('bundled', None)

        cp = super().create(validated_data)

        if addons_data:
            for addon_data in addons_data:
                addon_data['addon_to'] = cp
                addon_data['is_bundled'] = False
                addon_data['cart_id'] = cp.cart_id
                super().create(addon_data)

        if bundled_data:
            for bundle_data in bundled_data:
                bundle_data['addon_to'] = cp
                bundle_data['is_bundled'] = True
                bundle_data['cart_id'] = cp.cart_id
                super().create(bundle_data)

        return cp

    def validate(self, data):
        data = super().validate(data)

        # This is currently only a very basic validation of add-ons and bundled products, we don't validate their number
        # or price. We can always go stricter, as the endpoint is documented as experimental.
        # However, this serializer should always be *at least* as strict as the order creation serializer.

        if data.get('item') and data.get('addons'):
            prefetch_related_objects([data['item']], 'addons')
            for sub_data in data['addons']:
                if not any(a.addon_category_id == sub_data['item'].category_id for a in data['item'].addons.all()):
                    raise ValidationError({
                        'addons': [
                            'The product "{prod}" can not be used as an add-on product for "{main}".'.format(
                                prod=str(sub_data['item']),
                                main=str(data['item']),
                            )
                        ]
                    })

        if data.get('item') and data.get('bundled'):
            prefetch_related_objects([data['item']], 'bundles')
            for sub_data in data['bundled']:
                if not any(
                    a.bundled_item_id == sub_data['item'].pk and
                    a.bundled_variation_id == (sub_data['variation'].pk if sub_data.get('variation') else None)
                    for a in data['item'].bundles.all()
                ):
                    raise ValidationError({
                        'bundled': [
                            'The product "{prod}" can not be used as an bundled product for "{main}".'.format(
                                prod=str(sub_data['item']),
                                main=str(data['item']),
                            )
                        ]
                    })
        return data
