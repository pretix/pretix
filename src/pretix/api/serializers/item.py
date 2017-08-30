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


class InlineItemAddOnSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemAddOn
        fields = ('addon_category', 'min_count', 'max_count',
                  'position')


class ItemTaxRateField(serializers.Field):
    def to_representation(self, i):
        if i.tax_rule:
            return str(Decimal(i.tax_rule.rate))
        else:
            return str(Decimal('0.00'))


class ItemSerializer(I18nAwareModelSerializer):
    addons = InlineItemAddOnSerializer(many=True)
    variations = InlineItemVariationSerializer(many=True)
    tax_rate = ItemTaxRateField(source='*', read_only=True)

    class Meta:
        model = Item
        fields = ('id', 'category', 'name', 'active', 'description',
                  'default_price', 'free_price', 'tax_rate', 'tax_rule', 'admission',
                  'position', 'picture', 'available_from', 'available_until',
                  'require_voucher', 'hide_without_voucher', 'allow_cancel',
                  'min_per_order', 'max_per_order', 'checkin_attention', 'has_variations',
                  'variations', 'addons')


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
