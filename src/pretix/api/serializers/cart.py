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
from django.db.models import Q
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.utils.translation import gettext_lazy
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import (
    AnswerCreateSerializer, AnswerSerializer, InlineSeatSerializer,
)
from pretix.base.models import Quota, Seat, Voucher
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
                  'answers', 'seat')


class CartPositionCreateSerializer(I18nAwareModelSerializer):
    answers = AnswerCreateSerializer(many=True, required=False)
    expires = serializers.DateTimeField(required=False)
    attendee_name = serializers.CharField(required=False, allow_null=True)
    seat = serializers.CharField(required=False, allow_null=True)
    sales_channel = serializers.CharField(required=False, default='sales_channel')
    includes_tax = serializers.BooleanField(required=False, allow_null=True)
    voucher = serializers.CharField(required=False, allow_null=True)

    class Meta:
        model = CartPosition
        fields = ('cart_id', 'item', 'variation', 'price', 'attendee_name', 'attendee_name_parts', 'attendee_email',
                  'subevent', 'expires', 'includes_tax', 'answers', 'seat', 'sales_channel', 'voucher')

    def create(self, validated_data):
        answers_data = validated_data.pop('answers')
        if not validated_data.get('cart_id'):
            cid = "{}@api".format(get_random_string(48))
            while CartPosition.objects.filter(cart_id=cid).exists():
                cid = "{}@api".format(get_random_string(48))
            validated_data['cart_id'] = cid

        if not validated_data.get('expires'):
            validated_data['expires'] = now() + timedelta(
                minutes=self.context['event'].settings.get('reservation_time', as_type=int)
            )

        new_quotas = (validated_data.get('variation').quotas.filter(subevent=validated_data.get('subevent'))
                      if validated_data.get('variation')
                      else validated_data.get('item').quotas.filter(subevent=validated_data.get('subevent')))
        if len(new_quotas) == 0:
            raise ValidationError(
                gettext_lazy('The product "{}" is not assigned to a quota.').format(
                    str(validated_data.get('item'))
                )
            )
        for quota in new_quotas:
            avail = quota.availability(_cache=self.context['quota_cache'])
            if avail[0] != Quota.AVAILABILITY_OK or (avail[1] is not None and avail[1] < 1):
                raise ValidationError(
                    gettext_lazy('There is not enough quota available on quota "{}" to perform '
                                 'the operation.').format(
                        quota.name
                    )
                )

        for quota in new_quotas:
            oldsize = self.context['quota_cache'][quota.pk][1]
            newsize = oldsize - 1 if oldsize is not None else None
            self.context['quota_cache'][quota.pk] = (
                Quota.AVAILABILITY_OK if newsize is None or newsize > 0 else Quota.AVAILABILITY_GONE,
                newsize
            )

        attendee_name = validated_data.pop('attendee_name', '')
        if attendee_name and not validated_data.get('attendee_name_parts'):
            validated_data['attendee_name_parts'] = {
                '_legacy': attendee_name
            }

        seated = validated_data.get('item').seat_category_mappings.filter(subevent=validated_data.get('subevent')).exists()
        if validated_data.get('seat'):
            if not seated:
                raise ValidationError('The specified product does not allow to choose a seat.')
            try:
                seat = self.context['event'].seats.get(seat_guid=validated_data['seat'], subevent=validated_data.get('subevent'))
            except Seat.DoesNotExist:
                raise ValidationError('The specified seat does not exist.')
            except Seat.MultipleObjectsReturned:
                raise ValidationError('The specified seat ID is not unique.')
            else:
                validated_data['seat'] = seat
        elif seated:
            raise ValidationError('The specified product requires to choose a seat.')

        if validated_data.get('voucher'):
            try:
                voucher = self.context['event'].vouchers.get(code__iexact=validated_data.get('voucher'))
            except Voucher.DoesNotExist:
                raise ValidationError('The specified voucher does not exist.')

            if voucher and not voucher.applies_to(validated_data.get('item'), validated_data.get('variation')):
                raise ValidationError('The specified voucher is not valid for the given item and variation.')

            if voucher and voucher.seat and voucher.seat != validated_data.get('seat'):
                raise ValidationError('The specified voucher is not valid for this seat.')

            if voucher and voucher.subevent_id and (not validated_data.get('subevent') or voucher.subevent_id != validated_data['subevent'].pk):
                raise ValidationError('The specified voucher is not valid for this subevent.')

            if voucher.valid_until is not None and voucher.valid_until < now():
                raise ValidationError('The specified voucher is expired.')

            redeemed_in_carts = CartPosition.objects.filter(
                Q(voucher=voucher) & Q(event=self.context['event']) & Q(expires__gte=now())
            )
            cart_count = redeemed_in_carts.count()
            v_avail = voucher.max_usages - voucher.redeemed - cart_count
            if v_avail < 1:
                raise ValidationError('The specified voucher has already been used the maximum number of times.')

            validated_data['voucher'] = voucher

        if validated_data.get('seat'):
            if not validated_data['seat'].is_available(
                sales_channel=validated_data.get('sales_channel', 'web'),
                distance_ignore_cart_id=validated_data['cart_id'],
                ignore_voucher_id=validated_data['voucher'].pk if validated_data.get('voucher') else None,
            ):
                raise ValidationError(
                    gettext_lazy('The selected seat "{seat}" is not available.').format(seat=validated_data['seat'].name))

        validated_data.pop('sales_channel')
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

    def validate_cart_id(self, cid):
        if cid and not cid.endswith('@api'):
            raise ValidationError('Cart ID should end in @api or be empty.')
        return cid

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
        return data
