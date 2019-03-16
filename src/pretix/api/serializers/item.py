from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import (
    Item, ItemAddOn, ItemBundle, ItemCategory, ItemVariation, Question,
    QuestionOption, Quota,
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


class InlineItemBundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemBundle
        fields = ('bundled_item', 'bundled_variation', 'count',
                  'designated_price')


class InlineItemAddOnSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemAddOn
        fields = ('addon_category', 'min_count', 'max_count',
                  'position', 'price_included')


class ItemBundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemBundle
        fields = ('id', 'bundled_item', 'bundled_variation', 'count',
                  'designated_price')

    def validate(self, data):
        data = super().validate(data)
        event = self.context['event']

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        ItemBundle.clean_itemvar(event, full_data.get('bundled_item'), full_data.get('bundled_variation'))

        item = self.context['item']
        if item == full_data.get('bundled_item'):
            raise ValidationError(_("The bundled item must not be the same item as the bundling one."))
        if full_data.get('bundled_item'):
            if full_data['bundled_item'].bundles.exists():
                raise ValidationError(_("The bundled item must not have bundles on its own."))

        return data


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
    bundles = InlineItemBundleSerializer(many=True, required=False)
    variations = InlineItemVariationSerializer(many=True, required=False)
    tax_rate = ItemTaxRateField(source='*', read_only=True)

    class Meta:
        model = Item
        fields = ('id', 'category', 'name', 'internal_name', 'active', 'sales_channels', 'description',
                  'default_price', 'free_price', 'tax_rate', 'tax_rule', 'admission',
                  'position', 'picture', 'available_from', 'available_until',
                  'require_voucher', 'hide_without_voucher', 'allow_cancel',
                  'min_per_order', 'max_per_order', 'checkin_attention', 'has_variations', 'variations',
                  'addons', 'bundles', 'original_price', 'require_approval', 'generate_tickets')
        read_only_fields = ('has_variations', 'picture')

    def get_serializer_context(self):
        return {"has_variations": self.kwargs['has_variations']}

    def validate(self, data):
        data = super().validate(data)
        if self.instance and ('addons' in data or 'variations' in data or 'bundles' in data):
            raise ValidationError(_('Updating add-ons, bundles, or variations via PATCH/PUT is not supported. Please use the '
                                    'dedicated nested endpoint.'))

        Item.clean_per_order(data.get('min_per_order'), data.get('max_per_order'))
        Item.clean_available(data.get('available_from'), data.get('available_until'))

        return data

    def validate_category(self, value):
        Item.clean_category(value, self.context['event'])
        return value

    def validate_tax_rule(self, value):
        Item.clean_tax_rule(value, self.context['event'])
        return value

    def validate_bundles(self, value):
        if not self.instance:
            for b_data in value:
                ItemBundle.clean_itemvar(self.context['event'], b_data['bundled_item'], b_data['bundled_variation'])
        return value

    def validate_addons(self, value):
        if not self.instance:
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
        bundles_data = validated_data.pop('bundles') if 'bundles' in validated_data else {}
        item = Item.objects.create(**validated_data)
        for variation_data in variations_data:
            ItemVariation.objects.create(item=item, **variation_data)
        for addon_data in addons_data:
            ItemAddOn.objects.create(base_item=item, **addon_data)
        for bundle_data in bundles_data:
            ItemBundle.objects.create(base_item=item, **bundle_data)
        return item


class ItemCategorySerializer(I18nAwareModelSerializer):

    class Meta:
        model = ItemCategory
        fields = ('id', 'name', 'internal_name', 'description', 'position', 'is_addon')


class QuestionOptionSerializer(I18nAwareModelSerializer):
    identifier = serializers.CharField(allow_null=True)

    class Meta:
        model = QuestionOption
        fields = ('id', 'identifier', 'answer', 'position')

    def validate_identifier(self, value):
        QuestionOption.clean_identifier(self.context['event'], value, self.instance)
        return value


class InlineQuestionOptionSerializer(I18nAwareModelSerializer):
    identifier = serializers.CharField(allow_null=True)

    class Meta:
        model = QuestionOption
        fields = ('id', 'identifier', 'answer', 'position')


class QuestionSerializer(I18nAwareModelSerializer):
    options = InlineQuestionOptionSerializer(many=True, required=False)
    identifier = serializers.CharField(allow_null=True)

    class Meta:
        model = Question
        fields = ('id', 'question', 'type', 'required', 'items', 'options', 'position',
                  'ask_during_checkin', 'identifier', 'dependency_question', 'dependency_value')

    def validate_identifier(self, value):
        Question._clean_identifier(self.context['event'], value, self.instance)
        return value

    def validate_dependency_question(self, value):
        if value:
            if value.type not in (Question.TYPE_CHOICE, Question.TYPE_BOOLEAN, Question.TYPE_CHOICE_MULTIPLE):
                raise ValidationError('Question dependencies can only be set to boolean or choice questions.')
        if value == self.instance:
            raise ValidationError('A question cannot depend on itself.')
        return value

    def validate(self, data):
        data = super().validate(data)
        if self.instance and 'options' in data:
            raise ValidationError(_('Updating options via PATCH/PUT is not supported. Please use the dedicated'
                                    ' nested endpoint.'))

        event = self.context['event']

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        if full_data.get('ask_during_checkin') and full_data.get('dependency_question'):
            raise ValidationError('Dependencies are not supported during check-in.')

        dep = full_data.get('dependency_question')
        if dep:
            seen_ids = {self.instance.pk} if self.instance else set()
            while dep:
                if dep.pk in seen_ids:
                    raise ValidationError(_('Circular dependency between questions detected.'))
                seen_ids.add(dep.pk)
                dep = dep.dependency_question

        Question.clean_items(event, full_data.get('items'))
        return data

    def validate_options(self, value):
        if not self.instance:
            known = []
            for opt_data in value:
                if opt_data.get('identifier'):
                    QuestionOption.clean_identifier(self.context['event'], opt_data.get('identifier'), self.instance,
                                                    known)
                    known.append(opt_data.get('identifier'))
        return value

    @transaction.atomic
    def create(self, validated_data):
        options_data = validated_data.pop('options') if 'options' in validated_data else []
        items = validated_data.pop('items')
        question = Question.objects.create(**validated_data)
        question.items.set(items)
        for opt_data in options_data:
            QuestionOption.objects.create(question=question, **opt_data)
        return question


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
