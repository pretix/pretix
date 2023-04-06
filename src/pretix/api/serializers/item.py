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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Patrick Arminio, Ture Gjørup, pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import os.path
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils.functional import cached_property, lazy
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from pretix.api.serializers.event import MetaDataField
from pretix.api.serializers.fields import UploadedFileField
from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import (
    Item, ItemAddOn, ItemBundle, ItemCategory, ItemMetaValue, ItemVariation,
    ItemVariationMetaValue, Question, QuestionOption, Quota,
)


class InlineItemVariationSerializer(I18nAwareModelSerializer):
    price = serializers.DecimalField(read_only=True, decimal_places=2, max_digits=13,
                                     coerce_to_string=True)
    meta_data = MetaDataField(required=False, source='*')

    class Meta:
        model = ItemVariation
        fields = ('id', 'value', 'active', 'description',
                  'position', 'default_price', 'price', 'original_price', 'require_approval',
                  'require_membership', 'require_membership_types', 'require_membership_hidden',
                  'checkin_attention', 'available_from', 'available_until',
                  'sales_channels', 'hide_without_voucher', 'meta_data')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['require_membership_types'].queryset = lazy(lambda: self.context['event'].organizer.membership_types.all(), QuerySet)

    def validate_meta_data(self, value):
        for key in value['meta_data'].keys():
            if key not in self.parent.parent.item_meta_properties:
                raise ValidationError(_('Item meta data property \'{name}\' does not exist.').format(name=key))
        return value


class ItemVariationSerializer(I18nAwareModelSerializer):
    price = serializers.DecimalField(read_only=True, decimal_places=2, max_digits=13,
                                     coerce_to_string=True)
    meta_data = MetaDataField(required=False, source='*')

    class Meta:
        model = ItemVariation
        fields = ('id', 'value', 'active', 'description',
                  'position', 'default_price', 'price', 'original_price', 'require_approval',
                  'require_membership', 'require_membership_types', 'require_membership_hidden',
                  'checkin_attention', 'available_from', 'available_until',
                  'sales_channels', 'hide_without_voucher', 'meta_data')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['require_membership_types'].queryset = self.context['event'].organizer.membership_types.all()

    @transaction.atomic
    def create(self, validated_data):
        meta_data = validated_data.pop('meta_data', None)
        require_membership_types = validated_data.pop('require_membership_types', [])
        variation = ItemVariation.objects.create(**validated_data)

        if require_membership_types:
            variation.require_membership_types.add(*require_membership_types)

        # Meta data
        if meta_data is not None:
            for key, value in meta_data.items():
                ItemVariationMetaValue.objects.create(
                    property=self.item_meta_properties.get(key),
                    value=value,
                    variation=variation
                )
        return variation

    @cached_property
    def item_meta_properties(self):
        return {
            p.name: p for p in self.context['request'].event.item_meta_properties.all()
        }

    def validate_meta_data(self, value):
        for key in value['meta_data'].keys():
            if key not in self.item_meta_properties:
                raise ValidationError(_('Item meta data property \'{name}\' does not exist.').format(name=key))
        return value

    def update(self, instance, validated_data):
        meta_data = validated_data.pop('meta_data', None)
        variation = super().update(instance, validated_data)

        # Meta data
        if meta_data is not None:
            current = {mv.property: mv for mv in variation.meta_values.select_related('property')}
            for key, value in meta_data.items():
                prop = self.item_meta_properties.get(key)
                if prop in current:
                    current[prop].value = value
                    current[prop].save()
                else:
                    variation.meta_values.create(
                        property=self.item_meta_properties.get(key),
                        value=value
                    )

            for prop, current_object in current.items():
                if prop.name not in meta_data:
                    current_object.delete()

        return variation


class InlineItemBundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemBundle
        fields = ('bundled_item', 'bundled_variation', 'count',
                  'designated_price')


class InlineItemAddOnSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemAddOn
        fields = ('addon_category', 'min_count', 'max_count',
                  'position', 'price_included', 'multi_allowed')


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
                  'position', 'price_included', 'multi_allowed')

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
    meta_data = MetaDataField(required=False, source='*')
    picture = UploadedFileField(required=False, allow_null=True, allowed_types=(
        'image/png', 'image/jpeg', 'image/gif'
    ), max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE)

    class Meta:
        model = Item
        fields = ('id', 'category', 'name', 'internal_name', 'active', 'sales_channels', 'description',
                  'default_price', 'free_price', 'tax_rate', 'tax_rule', 'admission', 'personalized',
                  'position', 'picture', 'available_from', 'available_until',
                  'require_voucher', 'hide_without_voucher', 'allow_cancel', 'require_bundling',
                  'min_per_order', 'max_per_order', 'checkin_attention', 'has_variations', 'variations',
                  'addons', 'bundles', 'original_price', 'require_approval', 'generate_tickets',
                  'show_quota_left', 'hidden_if_available', 'allow_waitinglist', 'issue_giftcard', 'meta_data',
                  'require_membership', 'require_membership_types', 'require_membership_hidden', 'grant_membership_type',
                  'grant_membership_duration_like_event', 'grant_membership_duration_days',
                  'grant_membership_duration_months', 'validity_mode', 'validity_fixed_from', 'validity_fixed_until',
                  'validity_dynamic_duration_minutes', 'validity_dynamic_duration_hours', 'validity_dynamic_duration_days',
                  'validity_dynamic_duration_months', 'validity_dynamic_start_choice', 'validity_dynamic_start_choice_day_limit',
                  'media_policy', 'media_type')
        read_only_fields = ('has_variations',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['default_price'].allow_null = False
        self.fields['default_price'].required = True
        if not self.read_only:
            self.fields['require_membership_types'].queryset = self.context['event'].organizer.membership_types.all()
            self.fields['grant_membership_type'].queryset = self.context['event'].organizer.membership_types.all()

    def validate(self, data):
        data = super().validate(data)
        if self.instance and ('addons' in data or 'variations' in data or 'bundles' in data):
            raise ValidationError(_('Updating add-ons, bundles, or variations via PATCH/PUT is not supported. Please use the '
                                    'dedicated nested endpoint.'))

        Item.clean_per_order(data.get('min_per_order'), data.get('max_per_order'))
        Item.clean_available(data.get('available_from'), data.get('available_until'))
        Item.clean_media_settings(self.context['event'], data.get('media_policy'), data.get('media_type'), data.get('issue_giftcard'))

        if data.get('personalized') and not data.get('admission'):
            raise ValidationError(_('Only admission products can currently be personalized.'))

        if data.get('admission') and 'personalized' not in data and not self.instance:
            # Backwards compatibility
            data['personalized'] = True
        elif 'admission' in data and not data['admission']:
            data['personalized'] = False

        if data.get('issue_giftcard'):
            if data.get('tax_rule') and data.get('tax_rule').rate > 0:
                raise ValidationError(
                    _("Gift card products should not be associated with non-zero tax rates since sales tax will be "
                      "applied when the gift card is redeemed.")
                )
            if data.get('admission'):
                raise ValidationError(_(
                    "Gift card products should not be admission products at the same time."
                ))

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
                ItemAddOn.clean_min_count(addon_data.get('min_count', 0))
                ItemAddOn.clean_max_count(addon_data.get('max_count', 0))
                ItemAddOn.clean_max_min_count(addon_data.get('max_count', 0), addon_data.get('min_count', 0))
        return value

    @cached_property
    def item_meta_properties(self):
        return {
            p.name: p for p in self.context['request'].event.item_meta_properties.all()
        }

    def validate_meta_data(self, value):
        for key in value['meta_data'].keys():
            if key not in self.item_meta_properties:
                raise ValidationError(_('Item meta data property \'{name}\' does not exist.').format(name=key))
        return value

    @transaction.atomic
    def create(self, validated_data):
        variations_data = validated_data.pop('variations') if 'variations' in validated_data else {}
        addons_data = validated_data.pop('addons') if 'addons' in validated_data else {}
        bundles_data = validated_data.pop('bundles') if 'bundles' in validated_data else {}
        meta_data = validated_data.pop('meta_data', None)
        picture = validated_data.pop('picture', None)
        require_membership_types = validated_data.pop('require_membership_types', [])
        item = Item.objects.create(**validated_data)
        if picture:
            item.picture.save(os.path.basename(picture.name), picture)
        if require_membership_types:
            item.require_membership_types.add(*require_membership_types)

        for variation_data in variations_data:
            require_membership_types = variation_data.pop('require_membership_types', [])
            var_meta_data = variation_data.pop('meta_data', {})
            v = ItemVariation.objects.create(item=item, **variation_data)
            if require_membership_types:
                v.require_membership_types.add(*require_membership_types)

            if var_meta_data is not None:
                for key, value in var_meta_data.items():
                    ItemVariationMetaValue.objects.create(
                        property=self.item_meta_properties.get(key),
                        value=value,
                        variation=v
                    )

        for addon_data in addons_data:
            ItemAddOn.objects.create(base_item=item, **addon_data)
        for bundle_data in bundles_data:
            ItemBundle.objects.create(base_item=item, **bundle_data)

        # Meta data
        if meta_data is not None:
            for key, value in meta_data.items():
                ItemMetaValue.objects.create(
                    property=self.item_meta_properties.get(key),
                    value=value,
                    item=item
                )
        return item

    def update(self, instance, validated_data):
        meta_data = validated_data.pop('meta_data', None)
        picture = validated_data.pop('picture', None)
        item = super().update(instance, validated_data)
        if picture:
            item.picture.save(os.path.basename(picture.name), picture)

        # Meta data
        if meta_data is not None:
            current = {mv.property: mv for mv in item.meta_values.select_related('property')}
            for key, value in meta_data.items():
                prop = self.item_meta_properties.get(key)
                if prop in current:
                    current[prop].value = value
                    current[prop].save()
                else:
                    item.meta_values.create(
                        property=self.item_meta_properties.get(key),
                        value=value
                    )

            for prop, current_object in current.items():
                if prop.name not in meta_data:
                    current_object.delete()

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


class LegacyDependencyValueField(serializers.CharField):

    def to_representation(self, obj):
        return obj[0] if obj else None

    def to_internal_value(self, data):
        return [data] if data else []


class QuestionSerializer(I18nAwareModelSerializer):
    options = InlineQuestionOptionSerializer(many=True, required=False)
    identifier = serializers.CharField(allow_null=True)
    dependency_value = LegacyDependencyValueField(source='dependency_values', required=False, allow_null=True)

    class Meta:
        model = Question
        fields = ('id', 'question', 'type', 'required', 'items', 'options', 'position',
                  'ask_during_checkin', 'identifier', 'dependency_question', 'dependency_values',
                  'hidden', 'dependency_value', 'print_on_invoice', 'help_text', 'valid_number_min',
                  'valid_number_max', 'valid_date_min', 'valid_date_max', 'valid_datetime_min', 'valid_datetime_max',
                  'valid_string_length_max', 'valid_file_portrait')

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
            if dep.ask_during_checkin:
                raise ValidationError(_('Question cannot depend on a question asked during check-in.'))

            seen_ids = {self.instance.pk} if self.instance else set()
            while dep:
                if dep.pk in seen_ids:
                    raise ValidationError(_('Circular dependency between questions detected.'))
                seen_ids.add(dep.pk)
                dep = dep.dependency_question

        if full_data.get('ask_during_checkin') and full_data.get('type') in Question.ASK_DURING_CHECKIN_UNSUPPORTED:
            raise ValidationError(_('This type of question cannot be asked during check-in.'))

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
    available = serializers.BooleanField(read_only=True)
    available_number = serializers.IntegerField(read_only=True)

    class Meta:
        model = Quota
        fields = ('id', 'name', 'size', 'items', 'variations', 'subevent', 'closed', 'close_when_sold_out',
                  'release_after_exit', 'available', 'available_number')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'request' not in self.context or self.context['request'].GET.get('with_availability') != 'true':
            del self.fields['available']
            del self.fields['available_number']

    def validate(self, data):
        data = super().validate(data)
        event = self.context['event']

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        Quota.clean_variations(full_data.get('items'), full_data.get('variations'))
        Quota.clean_items(event, full_data.get('items'), full_data.get('variations'))
        Quota.clean_subevent(event, full_data.get('subevent'))

        return data
