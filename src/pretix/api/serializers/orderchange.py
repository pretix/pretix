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
import logging
import os

import pycountry
from django.core.files import File
from django.core.validators import RegexValidator
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.order import (
    AnswerCreateSerializer, AnswerSerializer, CompatibleCountryField,
    OrderPositionCreateSerializer,
)
from pretix.base.models import ItemVariation, Order, OrderFee, OrderPosition
from pretix.base.services.orders import OrderError
from pretix.base.settings import COUNTRIES_WITH_STATE_IN_ADDRESS

logger = logging.getLogger(__name__)


class OrderPositionCreateForExistingOrderSerializer(OrderPositionCreateSerializer):
    order = serializers.SlugRelatedField(slug_field='code', queryset=Order.objects.none(), required=True, allow_null=False)
    answers = AnswerCreateSerializer(many=True, required=False)
    addon_to = serializers.IntegerField(required=False, allow_null=True)
    secret = serializers.CharField(required=False)
    attendee_name = serializers.CharField(required=False, allow_null=True)
    seat = serializers.CharField(required=False, allow_null=True)
    price = serializers.DecimalField(required=False, allow_null=True, decimal_places=2,
                                     max_digits=13)
    country = CompatibleCountryField(source='*')

    class Meta:
        model = OrderPosition
        fields = ('order', 'item', 'variation', 'price', 'attendee_name', 'attendee_name_parts', 'attendee_email',
                  'company', 'street', 'zipcode', 'city', 'country', 'state',
                  'secret', 'addon_to', 'subevent', 'answers', 'seat', 'valid_from', 'valid_until')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.context:
            return
        self.fields['order'].queryset = self.context['event'].orders.all()
        self.fields['item'].queryset = self.context['event'].items.all()
        self.fields['subevent'].queryset = self.context['event'].subevents.all()
        self.fields['seat'].queryset = self.context['event'].seats.all()
        self.fields['variation'].queryset = ItemVariation.objects.filter(item__event=self.context['event'])
        if 'order' in self.context:
            del self.fields['order']

    def validate(self, data):
        data = super().validate(data)
        if 'order' in self.context:
            data['order'] = self.context['order']
        if data.get('addon_to'):
            try:
                data['addon_to'] = data['order'].positions.get(positionid=data['addon_to'])
            except OrderPosition.DoesNotExist:
                raise ValidationError({
                    'addon_to': ['addon_to refers to an unknown position ID for this order.']
                })
        return data

    def create(self, validated_data):
        ocm = self.context['ocm']

        try:
            ocm.add_position(
                item=validated_data['item'],
                variation=validated_data.get('variation'),
                price=validated_data.get('price'),
                addon_to=validated_data.get('addon_to'),
                subevent=validated_data.get('subevent'),
                seat=validated_data.get('seat'),
                valid_from=validated_data.get('valid_from'),
                valid_until=validated_data.get('valid_until'),
            )
            if self.context.get('commit', True):
                ocm.commit()
                return validated_data['order'].positions.order_by('-positionid').first()
            else:
                return OrderPosition()  # fake to appease DRF
        except OrderError as e:
            raise ValidationError(str(e))


class OrderPositionInfoPatchSerializer(serializers.ModelSerializer):
    answers = AnswerSerializer(many=True)
    country = CompatibleCountryField(source='*')
    attendee_name = serializers.CharField(required=False)

    class Meta:
        model = OrderPosition
        fields = (
            'attendee_name', 'attendee_name_parts', 'company', 'street', 'zipcode', 'city', 'country',
            'state', 'attendee_email', 'answers',
        )

    def validate(self, data):
        if data.get('attendee_name') and data.get('attendee_name_parts'):
            raise ValidationError(
                {'attendee_name': ['Do not specify attendee_name if you specified attendee_name_parts.']}
            )
        if data.get('attendee_name_parts') and '_scheme' not in data.get('attendee_name_parts'):
            data['attendee_name_parts']['_scheme'] = self.context['request'].event.settings.name_scheme

        if data.get('country'):
            if not pycountry.countries.get(alpha_2=data.get('country').code):
                raise ValidationError(
                    {'country': ['Invalid country code.']}
                )

        if data.get('state'):
            cc = str(data.get('country') or self.instance.country or '')
            if cc not in COUNTRIES_WITH_STATE_IN_ADDRESS:
                raise ValidationError(
                    {'state': ['States are not supported in country "{}".'.format(cc)]}
                )
            if not pycountry.subdivisions.get(code=cc + '-' + data.get('state')):
                raise ValidationError(
                    {'state': ['"{}" is not a known subdivision of the country "{}".'.format(data.get('state'), cc)]}
                )
        return data

    def update(self, instance, validated_data):
        answers_data = validated_data.pop('answers', None)

        name = validated_data.pop('attendee_name', '')
        if name and not validated_data.get('attendee_name_parts'):
            validated_data['attendee_name_parts'] = {
                '_legacy': name
            }

        for attr, value in validated_data.items():
            if attr in self.fields:
                setattr(instance, attr, value)

        instance.save(update_fields=list(validated_data.keys()))

        if answers_data is not None:
            qs_seen = set()
            answercache = {
                a.question_id: a for a in instance.answers.all()
            }
            for answ_data in answers_data:
                if not answ_data.get('answer'):
                    continue
                options = answ_data.pop('options', [])
                if answ_data['question'].pk in qs_seen:
                    raise ValidationError(f'Question {answ_data["question"]} was sent twice.')
                if answ_data['question'].pk in answercache:
                    a = answercache[answ_data['question'].pk]
                    if isinstance(answ_data.get('answer'), File):
                        a.file.save(answ_data['answer'].name, answ_data['answer'], save=False)
                        a.answer = 'file://' + a.file.name
                    elif a.answer.startswith('file://') and answ_data['answer'] == "file:keep":
                        pass  # keep current file
                    else:
                        for attr, value in answ_data.items():
                            setattr(a, attr, value)
                    a.save()
                else:
                    if isinstance(answ_data.get('answer'), File):
                        an = answ_data.pop('answer')
                        a = instance.answers.create(**answ_data, answer='')
                        a.file.save(os.path.basename(an.name), an, save=False)
                        a.answer = 'file://' + a.file.name
                        a.save()
                    else:
                        a = instance.answers.create(**answ_data)
                a.options.set(options)
                qs_seen.add(a.question_id)
            for qid, a in answercache.items():
                if qid not in qs_seen:
                    a.delete()

        return instance


class OrderPositionChangeSerializer(serializers.ModelSerializer):
    seat = serializers.CharField(source='seat.seat_guid', allow_null=True, required=False)

    class Meta:
        model = OrderPosition
        fields = (
            'item', 'variation', 'subevent', 'seat', 'price', 'tax_rule', 'valid_from', 'valid_until'
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.context:
            return
        self.fields['item'].queryset = self.context['event'].items.all()
        self.fields['subevent'].queryset = self.context['event'].subevents.all()
        self.fields['tax_rule'].queryset = self.context['event'].tax_rules.all()
        if kwargs.get('partial'):
            for k, v in self.fields.items():
                self.fields[k].required = False

    def validate_item(self, item):
        if item.event != self.context['event']:
            raise ValidationError(
                'The specified item does not belong to this event.'
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

    def validate(self, data, instance=None):
        instance = instance or self.instance
        if instance is None:
            return data  # needs to be done later
        if data.get('item', instance.item):
            if data.get('item', instance.item).has_variations:
                if not data.get('variation', instance.variation):
                    raise ValidationError({'variation': ['You should specify a variation for this item.']})
                else:
                    if data.get('variation', instance.variation).item != data.get('item', instance.item):
                        raise ValidationError(
                            {'variation': ['The specified variation does not belong to the specified item.']}
                        )
            elif data.get('variation', instance.variation):
                raise ValidationError(
                    {'variation': ['You cannot specify a variation for this item.']}
                )

        return data

    def update(self, instance, validated_data):
        ocm = self.context['ocm']
        current_seat = {'seat_guid': instance.seat.seat_guid} if instance.seat else None
        item = validated_data.get('item', instance.item)
        variation = validated_data.get('variation', instance.variation)
        subevent = validated_data.get('subevent', instance.subevent)
        price = validated_data.get('price', instance.price)
        seat = validated_data.get('seat', current_seat)
        tax_rule = validated_data.get('tax_rule', instance.tax_rule)
        valid_from = validated_data.get('valid_from', instance.valid_from)
        valid_until = validated_data.get('valid_until', instance.valid_until)

        change_item = None
        if item != instance.item or variation != instance.variation:
            change_item = (item, variation)

        change_subevent = None
        if self.context['event'].has_subevents and subevent != instance.subevent:
            change_subevent = (subevent,)

        try:
            if change_item is not None and change_subevent is not None:
                ocm.change_item_and_subevent(instance, *change_item, *change_subevent)
            elif change_item is not None:
                ocm.change_item(instance, *change_item)
            elif change_subevent is not None:
                ocm.change_subevent(instance, *change_subevent)

            if seat != current_seat or change_subevent:
                ocm.change_seat(instance, seat['seat_guid'] if seat else None)

            if price != instance.price:
                ocm.change_price(instance, price)

            if tax_rule != instance.tax_rule:
                ocm.change_tax_rule(instance, tax_rule)

            if valid_from != instance.valid_from:
                ocm.change_valid_from(instance, valid_from)

            if valid_until != instance.valid_until:
                ocm.change_valid_until(instance, valid_until)

            if self.context.get('commit', True):
                ocm.commit()
                instance.refresh_from_db()
        except OrderError as e:
            raise ValidationError(str(e))
        return instance


class PatchPositionSerializer(serializers.Serializer):
    position = serializers.PrimaryKeyRelatedField(queryset=OrderPosition.all.none())

    def validate_position(self, value):
        self.fields['body'].instance = value  # hack around DRFs validation order
        return value

    def validate(self, data):
        OrderPositionChangeSerializer(context=self.context, partial=True).validate(data['body'], data['position'])
        return data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['position'].queryset = self.context['order'].positions.all()
        self.fields['body'] = OrderPositionChangeSerializer(context=self.context, partial=True)


class SelectPositionSerializer(serializers.Serializer):
    position = serializers.PrimaryKeyRelatedField(queryset=OrderPosition.all.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['position'].queryset = self.context['order'].positions.all()


class OrderFeeChangeSerializer(serializers.ModelSerializer):

    class Meta:
        model = OrderFee
        fields = (
            'value',
        )

    def update(self, instance, validated_data):
        ocm = self.context['ocm']
        value = validated_data.get('value', instance.value)

        try:
            if value != instance.value:
                ocm.change_fee(instance, value)

            if self.context.get('commit', True):
                ocm.commit()
                instance.refresh_from_db()
        except OrderError as e:
            raise ValidationError(str(e))
        return instance


class PatchFeeSerializer(serializers.Serializer):
    fee = serializers.PrimaryKeyRelatedField(queryset=OrderFee.all.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fee'].queryset = self.context['order'].fees.all()
        self.fields['body'] = OrderFeeChangeSerializer(context=self.context)


class SelectFeeSerializer(serializers.Serializer):
    fee = serializers.PrimaryKeyRelatedField(queryset=OrderFee.all.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.context:
            return
        self.fields['fee'].queryset = self.context['order'].fees.all()


class OrderChangeOperationSerializer(serializers.Serializer):
    send_email = serializers.BooleanField(default=False, required=False)
    reissue_invoice = serializers.BooleanField(default=True, required=False)
    recalculate_taxes = serializers.ChoiceField(default=None, allow_null=True, required=False, choices=[
        ('keep_net', 'keep_net'),
        ('keep_gross', 'keep_gross'),
    ])

    def __init__(self, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self.fields['patch_positions'] = PatchPositionSerializer(
            many=True, required=False, context=self.context
        )
        self.fields['cancel_positions'] = SelectPositionSerializer(
            many=True, required=False, context=self.context
        )
        self.fields['create_positions'] = OrderPositionCreateForExistingOrderSerializer(
            many=True, required=False, context=self.context
        )
        self.fields['split_positions'] = SelectPositionSerializer(
            many=True, required=False, context=self.context
        )
        self.fields['patch_fees'] = PatchFeeSerializer(
            many=True, required=False, context=self.context
        )
        self.fields['cancel_fees'] = SelectFeeSerializer(
            many=True, required=False, context=self.context
        )

    def validate(self, data):
        seen_positions = set()
        for d in data.get('patch_positions', []):
            if d['position'] in seen_positions:
                raise ValidationError({'patch_positions': ['You have specified the same object twice.']})
            seen_positions.add(d['position'])
        seen_positions = set()
        for d in data.get('cancel_positions', []):
            if d['position'] in seen_positions:
                raise ValidationError({'cancel_positions': ['You have specified the same object twice.']})
            seen_positions.add(d['position'])
        seen_positions = set()
        for d in data.get('split_positions', []):
            if d['position'] in seen_positions:
                raise ValidationError({'split_positions': ['You have specified the same object twice.']})
            seen_positions.add(d['position'])
        seen_fees = set()
        for d in data.get('patch_fees', []):
            if d['fee'] in seen_fees:
                raise ValidationError({'patch_fees': ['You have specified the same object twice.']})
            seen_positions.add(d['fee'])
        seen_fees = set()
        for d in data.get('cancel_fees', []):
            if d['fee'] in seen_fees:
                raise ValidationError({'cancel_fees': ['You have specified the same object twice.']})
            seen_positions.add(d['fee'])

        return data


class BlockNameSerializer(serializers.Serializer):
    name = serializers.CharField(validators=[RegexValidator('^(admin|api:[a-zA-Z0-9._]+)$')])
