from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import ugettext_lazy as _
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

        ItemAddOn.clean_max_min_count(data.get('max_count'), data.get('min_count'))

        return data

    def validate_min_count(self, value):
        ItemAddOn.clean_min_count(value)
        return value

    def validate_max_count(self, value):
        ItemAddOn.clean_max_count(value)
        return value

    def validate_addon_category(self, value):
        ItemAddOn.clean_categories(self.context['event'], self.context['item'], self.instance, value)
        return value


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
        read_only_fields = ('has_variations', 'picture')

    def get_serializer_context(self):
        return {"has_variations": self.kwargs['has_variations']}

    def validate(self, data):
        data = super().validate(data)

        Item.clean_per_order(data.get('min_per_order'), data.get('max_per_order'))
        Item.clean_available(data.get('available_from'), data.get('available_until'))

        return data

    def validate_category(self, value):
        Item.clean_category(value, self.context['event'])
        return value

    def validate_tax_rule(self, value):
        Item.clean_tax_rule(value, self.context['event'])
        return value

    def validate_variations(self, value):
        if self.instance is not None:
            raise ValidationError(_('Updating variations via PATCH/PUT is not supported. Please use the dedicated'
                                    ' nested endpoint.'))
        return value

    def validate_addons(self, value):
        if self.instance is not None:
            raise ValidationError(_('Updating add-ons via PATCH/PUT is not supported. Please use the dedicated'
                                    ' nested endpoint.'))
        else:
            for addon_data in value:
                ItemAddOn.clean_categories(self.context['event'], None, self.instance, addon_data['addon_category'])
                ItemAddOn.clean_min_count(addon_data['min_count'])
                ItemAddOn.clean_max_count(addon_data['max_count'])
                ItemAddOn.clean_max_min_count(addon_data['max_count'], addon_data['min_count'])
        return value

    @transaction.atomic
    def create(self, validated_data):
        variations_data = validated_data.pop('variations') if 'variations' in validated_data else {}
        addons_data = validated_data.pop('addons') if 'addons' in validated_data else {}
        item = Item.objects.create(**validated_data)
        for variation_data in variations_data:
            ItemVariation.objects.create(item=item, **variation_data)
        for addon_data in addons_data:
            ItemAddOn.objects.create(base_item=item, **addon_data)
        return item


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
        fields = ('id', 'question', 'type', 'required', 'items', 'options', 'position',
                  'ask_during_checkin')


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
