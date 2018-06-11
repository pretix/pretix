from django.utils.crypto import get_random_string
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import (
    AnswerCreateSerializer, AnswerSerializer,
)
from pretix.base.models.orders import CartPosition


class CartPositionSerializer(I18nAwareModelSerializer):
    answers = AnswerSerializer(many=True)

    class Meta:
        model = CartPosition
        fields = ('id', 'cart_id', 'item', 'variation', 'price', 'attendee_name', 'attendee_email',
                  'voucher', 'addon_to', 'subevent', 'datetime', 'expires', 'includes_tax',
                  'answers',)


class CartPositionCreateSerializer(I18nAwareModelSerializer):
    answers = AnswerCreateSerializer(many=True, required=False)

    class Meta:
        model = CartPosition
        fields = ('cart_id', 'item', 'variation', 'price', 'attendee_name', 'attendee_email',
                  'subevent', 'expires', 'includes_tax', 'answers',)

    def create(self, validated_data):
        answers_data = validated_data.pop('answers')
        if not validated_data.get('cart_id'):
            cid = "{}@api".format(get_random_string(48))
            while CartPosition.objects.filter(cart_id=cid).exists():
                cid = "{}@api".format(get_random_string(48))
            validated_data['cart_id'] = cid
        cp = CartPosition.objects.create(event=self.context['event'], **validated_data)
        for answ_data in answers_data:
            options = answ_data.pop('options')
            answ = cp.answers.create(**answ_data)
            answ.options.add(*options)
        return cp

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
        return data
