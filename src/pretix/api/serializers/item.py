from rest_framework import serializers

from pretix.base.models import Item, ItemAddOn, ItemCategory, ItemVariation


class InlineItemVariationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemVariation
        fields = ('id', 'value', 'active', 'description',
                  'position', 'default_price', 'price')


class InlineItemAddOnSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemAddOn
        fields = ('addon_category', 'min_count', 'max_count',
                  'position')


class ItemSerializer(serializers.ModelSerializer):
    addons = InlineItemAddOnSerializer(many=True)
    variations = InlineItemVariationSerializer(many=True)

    class Meta:
        model = Item
        fields = ('id', 'category', 'name', 'active', 'description',
                  'default_price', 'free_price', 'tax_rate', 'admission',
                  'position', 'picture', 'available_from', 'available_until',
                  'require_voucher', 'hide_without_voucher', 'allow_cancel',
                  'min_per_order', 'max_per_order', 'has_variations',
                  'variations', 'addons')


class ItemCategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = ItemCategory
        fields = ('id', 'name', 'description', 'position', 'is_addon')
