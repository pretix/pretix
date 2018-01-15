from decimal import Decimal

from rest_framework import serializers

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import (
    Item, ItemAddOn, ItemCategory, ItemVariation, Question, QuestionOption,
    Quota,
)


class InlineItemVariationSerializer(I18nAwareModelSerializer):
    class Meta:
        model = ItemVariation
        fields = ('id', 'value', 'active', 'description',
                  'position', 'default_price', 'price')


class ItemVariationSerializer(I18nAwareModelSerializer):
    class Meta:
        model = ItemVariation
        fields = ('id', 'value', 'active', 'description',
                  'position', 'default_price', 'price')


class InlineItemAddOnSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemAddOn
        fields = ('addon_category', 'min_count', 'max_count',
                  'position', 'price_included')


class ItemAddOnSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemAddOn
        fields = ('id', 'addon_category', 'min_count', 'max_count',
                  'position', 'price_included')

    def validate(self, data):
        data = super().validate(data)
        item = self.context['item']

        ItemAddOn.clean_categories(item, self.instance, data.get('addon_category'))
        ItemAddOn.clean_max_min_numbers(data.get('max_count'), data.get('min_count'))

        return data


class ItemTaxRateField(serializers.Field):
    def to_representation(self, i):
        if i.tax_rule:
            return str(Decimal(i.tax_rule.rate))
        else:
            return str(Decimal('0.00'))


class ItemSerializer(I18nAwareModelSerializer):
    addons = InlineItemAddOnSerializer(many=True, required=False)
    variations = InlineItemVariationSerializer(many=True, required=False)
    tax_rate = ItemTaxRateField(source='*', read_only=True)

    class Meta:
        model = Item
        fields = ('id', 'category', 'name', 'active', 'description',
                  'default_price', 'free_price', 'tax_rate', 'tax_rule', 'admission',
                  'position', 'picture', 'available_from', 'available_until',
                  'require_voucher', 'hide_without_voucher', 'allow_cancel',
                  'min_per_order', 'max_per_order', 'checkin_attention', 'has_variations',
                  'variations', 'addons')
        read_only_fields = ('has_variations', 'picture', 'variations', 'addons')

    def validate(self, data):
        data = super().validate(data)
        event = self.context['event']

        Item.clean_per_order(data.get('min_per_order'), data.get('max_per_order'))
        Item.clean_available(data.get('available_from'), data.get('available_until'))
        Item.clean_category(data.get('category'), event)
        Item.clean_tax_rule(data.get('tax_rule'), event)

        return data


class ItemCategorySerializer(I18nAwareModelSerializer):

    class Meta:
        model = ItemCategory
        fields = ('id', 'name', 'description', 'position', 'is_addon')


class InlineQuestionOptionSerializer(I18nAwareModelSerializer):

    class Meta:
        model = QuestionOption
        fields = ('id', 'answer')


class QuestionSerializer(I18nAwareModelSerializer):
    options = InlineQuestionOptionSerializer(many=True)

    class Meta:
        model = Question
        fields = ('id', 'question', 'type', 'required', 'items', 'options', 'position')


class QuotaSerializer(I18nAwareModelSerializer):

    class Meta:
        model = Quota
        fields = ('id', 'name', 'size', 'items', 'variations', 'subevent')

    def validate(self, data):
        data = super().validate(data)
        event = self.context['event']

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        Quota.clean_variations(full_data.get('items'), full_data.get('variations'))
        Quota.clean_items(event, full_data.get('items'), full_data.get('variations'))
        Quota.clean_subevent(event, full_data.get('subevent'))

        return data
