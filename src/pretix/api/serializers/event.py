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
# This file contains Apache-licensed contributions copyrighted by: Ture Gjørup
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django_countries.serializers import CountryFieldMixin
from pytz import common_timezones
from rest_framework import serializers
from rest_framework.fields import ChoiceField, Field
from rest_framework.relations import SlugRelatedField

from pretix.api.serializers import CompatibleJSONField
from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.settings import SettingsSerializer
from pretix.base.models import Device, Event, TaxRule, TeamAPIToken
from pretix.base.models.event import SubEvent
from pretix.base.models.items import (
    ItemMetaProperty, SubEventItem, SubEventItemVariation,
)
from pretix.base.models.tax import CustomRulesValidator
from pretix.base.services.seating import (
    SeatProtected, generate_seats, validate_plan_change,
)
from pretix.base.settings import (
    PERSON_NAME_SALUTATIONS, PERSON_NAME_SCHEMES, PERSON_NAME_TITLE_GROUPS,
    LazyI18nStringList, validate_event_settings,
)
from pretix.base.signals import api_event_settings_fields
from pretix.multidomain.urlreverse import build_absolute_uri

logger = logging.getLogger(__name__)


class MetaDataField(Field):

    def to_representation(self, value):
        return {
            v.property.name: v.value for v in value.meta_values.all()
        }

    def to_internal_value(self, data):
        if not isinstance(data, dict) or not all(isinstance(k, str) for k in data.keys()):
            raise ValidationError('meta_data needs to be an object (str -> str).')

        return {
            'meta_data': data
        }


class MetaPropertyField(Field):

    def to_representation(self, value):
        return {
            v.name: v.default for v in value.item_meta_properties.all()
        }

    def to_internal_value(self, data):
        if not isinstance(data, dict) or not all(isinstance(k, str) for k in data.keys()) or not all(isinstance(k, str) for k in data.values()):
            raise ValidationError('item_meta_properties needs to be an object (str -> str).')
        return {
            'item_meta_properties': data
        }


class SeatCategoryMappingField(Field):

    def to_representation(self, value):
        if hasattr(value, '_seat_category_mappings'):
            qs = value._seat_category_mappings
        else:
            qs = value.seat_category_mappings.all()
            if isinstance(value, Event):
                qs = qs.filter(subevent=None)
        return {
            v.layout_category: v.product_id for v in qs
        }

    def to_internal_value(self, data):
        if not isinstance(data, dict) or not all(isinstance(k, str) for k in data.keys()) or not all(isinstance(k, int) for k in data.values()):
            raise ValidationError('seat_category_mapping needs to be an object (str -> int).')
        return {
            'seat_category_mapping': data or {}
        }


class PluginsField(Field):

    def to_representation(self, obj):
        from pretix.base.plugins import get_all_plugins

        return sorted([
            p.module for p in get_all_plugins()
            if not p.name.startswith('.') and getattr(p, 'visible', True) and p.module in obj.get_plugins()
        ])

    def to_internal_value(self, data):
        return {
            'plugins': data
        }


class TimeZoneField(ChoiceField):
    def get_attribute(self, instance):
        return instance.cache.get_or_set(
            'timezone_name',
            lambda: instance.settings.timezone,
            3600
        )


class ValidKeysField(Field):
    def to_representation(self, value):
        return value.cache.get_or_set(
            'ticket_secret_valid_keys',
            lambda: self._get(value),
            120
        )

    def _get(self, value):
        return {
            'pretix_sig1': [
                value.settings.ticket_secrets_pretix_sig1_pubkey
            ] if value.settings.ticket_secrets_pretix_sig1_pubkey else []
        }


class EventSerializer(I18nAwareModelSerializer):
    meta_data = MetaDataField(required=False, source='*')
    item_meta_properties = MetaPropertyField(required=False, source='*')
    plugins = PluginsField(required=False, source='*')
    seat_category_mapping = SeatCategoryMappingField(source='*', required=False)
    timezone = TimeZoneField(required=False, choices=[(a, a) for a in common_timezones])
    valid_keys = ValidKeysField(source='*', read_only=True)
    best_availability_state = serializers.IntegerField(allow_null=True, read_only=True)
    public_url = serializers.SerializerMethodField('get_event_url', read_only=True)

    def get_event_url(self, event):
        return build_absolute_uri(event, 'presale:event.index')

    class Meta:
        model = Event
        fields = ('name', 'slug', 'live', 'testmode', 'currency', 'date_from',
                  'date_to', 'date_admission', 'is_public', 'presale_start',
                  'presale_end', 'location', 'geo_lat', 'geo_lon', 'has_subevents', 'meta_data', 'seating_plan',
                  'plugins', 'seat_category_mapping', 'timezone', 'item_meta_properties', 'valid_keys',
                  'sales_channels', 'best_availability_state', 'public_url')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self.context['request'], 'event'):
            self.fields.pop('valid_keys')
        if not self.context.get('request') or 'with_availability_for' not in self.context['request'].GET:
            self.fields.pop('best_availability_state')

    def validate(self, data):
        data = super().validate(data)

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        Event.clean_dates(data.get('date_from'), data.get('date_to'))
        Event.clean_presale(data.get('presale_start'), data.get('presale_end'))

        if full_data.get('has_subevents') and full_data.get('seating_plan'):
            raise ValidationError('Event series should not directly be assigned a seating plan.')

        return data

    def validate_has_subevents(self, value):
        Event.clean_has_subevents(self.instance, value)
        return value

    def validate_slug(self, value):
        Event.clean_slug(self.context['request'].organizer, self.instance, value)
        return value

    def validate_live(self, value):
        if value:
            if self.instance is None:
                raise ValidationError(_('Events cannot be created as \'live\'. Quotas and payment must be added to the '
                                        'event before sales can go live.'))
            else:
                self.instance.clean_live()
        return value

    @cached_property
    def meta_properties(self):
        return {
            p.name: p for p in self.context['request'].organizer.meta_properties.all()
        }

    def validate_meta_data(self, value):
        for key, v in value['meta_data'].items():
            if key not in self.meta_properties:
                raise ValidationError(_('Meta data property \'{name}\' does not exist.').format(name=key))
            if self.meta_properties[key].allowed_values:
                if v not in [_v.strip() for _v in self.meta_properties[key].allowed_values.splitlines()]:
                    raise ValidationError(_('Meta data property \'{name}\' does not allow value \'{value}\'.').format(name=key, value=v))
        return value

    @cached_property
    def item_meta_props(self):
        return {
            p.name: p for p in self.context['request'].event.item_meta_properties.all()
        }

    def validate_seating_plan(self, value):
        if value and value.organizer != self.context['request'].organizer:
            raise ValidationError('Invalid seating plan.')
        if self.instance and self.instance.pk:
            try:
                validate_plan_change(self.instance, None, value)
            except SeatProtected as e:
                raise ValidationError(str(e))
        return value

    def validate_seat_category_mapping(self, value):
        if not self.instance or not self.instance.pk:
            if value and value['seat_category_mapping']:
                raise ValidationError('You cannot specify seat category mappings on event creation.')
            else:
                return {'seat_category_mapping': {}}
        item_cache = {i.pk: i for i in self.instance.items.all()}
        result = {}
        for k, item in value['seat_category_mapping'].items():
            if item not in item_cache:
                raise ValidationError('Item \'{id}\' does not exist.'.format(id=item))
            result[k] = item_cache[item]
        return {'seat_category_mapping': result}

    def validate_plugins(self, value):
        from pretix.base.plugins import get_all_plugins

        plugins_available = {
            p.module for p in get_all_plugins(self.instance)
            if not p.name.startswith('.') and getattr(p, 'visible', True)
        }

        for plugin in value.get('plugins'):
            if plugin not in plugins_available:
                raise ValidationError(_('Unknown plugin: \'{name}\'.').format(name=plugin))

        return value

    @cached_property
    def ignored_meta_properties(self):
        perm_holder = (self.context['request'].auth if isinstance(self.context['request'].auth, (Device, TeamAPIToken))
                       else self.context['request'].user)
        if perm_holder.has_organizer_permission(self.context['request'].organizer, 'can_change_organizer_settings', request=self.context['request']):
            return []
        return [k for k, p in self.meta_properties.items() if p.protected]

    @transaction.atomic
    def create(self, validated_data):
        meta_data = validated_data.pop('meta_data', None)
        item_meta_properties = validated_data.pop('item_meta_properties', None)
        validated_data.pop('seat_category_mapping', None)
        plugins = validated_data.pop('plugins', settings.PRETIX_PLUGINS_DEFAULT.split(','))
        tz = validated_data.pop('timezone', None)
        event = super().create(validated_data)

        if tz:
            event.settings.timezone = tz

        # Meta data
        if meta_data is not None:
            for key, value in meta_data.items():
                if key not in self.ignored_meta_properties:
                    event.meta_values.create(
                        property=self.meta_properties.get(key),
                        value=value
                    )

        # Item Meta properties
        if item_meta_properties is not None:
            for key, value in item_meta_properties.items():
                event.item_meta_properties.create(
                    name=key,
                    default=value,
                    event=event
                )

        # Seats
        if event.seating_plan:
            generate_seats(event, None, event.seating_plan, {})

        # Plugins
        if plugins is not None:
            event.set_active_plugins(plugins)
        event.save(update_fields=['plugins'])

        return event

    @transaction.atomic
    def update(self, instance, validated_data):
        meta_data = validated_data.pop('meta_data', None)
        item_meta_properties = validated_data.pop('item_meta_properties', None)
        plugins = validated_data.pop('plugins', None)
        seat_category_mapping = validated_data.pop('seat_category_mapping', None)
        tz = validated_data.pop('timezone', None)
        event = super().update(instance, validated_data)

        if tz:
            event.settings.timezone = tz

        # Meta data
        if meta_data is not None:
            current = {mv.property: mv for mv in event.meta_values.select_related('property')}
            for key, value in meta_data.items():
                if key not in self.ignored_meta_properties:
                    prop = self.meta_properties.get(key)
                    if prop in current:
                        current[prop].value = value
                        current[prop].save()
                    else:
                        event.meta_values.create(
                            property=self.meta_properties.get(key),
                            value=value
                        )

            for prop, current_object in current.items():
                if prop.name not in self.ignored_meta_properties:
                    if prop.name not in meta_data:
                        current_object.delete()

        # Item Meta properties
        if item_meta_properties is not None:
            current = list(event.item_meta_properties.all())
            for key, value in item_meta_properties.items():
                prop = self.item_meta_props.get(key)
                if prop in current:
                    prop.default = value
                    prop.save()
                else:
                    prop = event.item_meta_properties.create(
                        name=key,
                        default=value,
                        event=event
                    )
                    current.append(prop)

            for prop in current:
                if prop.name not in list(item_meta_properties.keys()):
                    prop.delete()

        # Seats
        if seat_category_mapping is not None or ('seating_plan' in validated_data and validated_data['seating_plan'] is None):
            current_mappings = {
                m.layout_category: m
                for m in event.seat_category_mappings.filter(subevent=None)
            }
            if not event.seating_plan:
                seat_category_mapping = {}
            for key, value in seat_category_mapping.items():
                if key in current_mappings:
                    m = current_mappings.pop(key)
                    m.product = value
                    m.save()
                else:
                    event.seat_category_mappings.create(product=value, layout_category=key)
            for m in current_mappings.values():
                m.delete()
        if 'seating_plan' in validated_data or seat_category_mapping is not None:
            generate_seats(event, None, event.seating_plan, {
                m.layout_category: m.product
                for m in event.seat_category_mappings.select_related('product').filter(subevent=None)
            })

        # Plugins
        if plugins is not None:
            event.set_active_plugins(plugins)
            event.save()

        return event


class CloneEventSerializer(EventSerializer):
    @transaction.atomic
    def create(self, validated_data):
        plugins = validated_data.pop('plugins', None)
        is_public = validated_data.pop('is_public', None)
        testmode = validated_data.pop('testmode', None)
        has_subevents = validated_data.pop('has_subevents', None)
        tz = validated_data.pop('timezone', None)
        sales_channels = validated_data.pop('sales_channels', None)
        date_admission = validated_data.pop('date_admission', None)
        new_event = super().create({**validated_data, 'plugins': None})

        event = Event.objects.filter(slug=self.context['event'], organizer=self.context['organizer'].pk).first()
        new_event.copy_data_from(event)

        if plugins is not None:
            new_event.set_active_plugins(plugins)
        if is_public is not None:
            new_event.is_public = is_public
        if testmode is not None:
            new_event.testmode = testmode
        if sales_channels is not None:
            new_event.sales_channels = sales_channels
        if has_subevents is not None:
            new_event.has_subevents = has_subevents
        if has_subevents is not None:
            new_event.has_subevents = has_subevents
        if date_admission is not None:
            new_event.date_admission = date_admission
        new_event.save()
        if tz:
            new_event.settings.timezone = tz

        return new_event


class SubEventItemSerializer(I18nAwareModelSerializer):
    class Meta:
        model = SubEventItem
        fields = ('item', 'price', 'disabled', 'available_from', 'available_until')


class SubEventItemVariationSerializer(I18nAwareModelSerializer):
    class Meta:
        model = SubEventItemVariation
        fields = ('variation', 'price', 'disabled', 'available_from', 'available_until')


class SubEventSerializer(I18nAwareModelSerializer):
    item_price_overrides = SubEventItemSerializer(source='subeventitem_set', many=True, required=False)
    variation_price_overrides = SubEventItemVariationSerializer(source='subeventitemvariation_set', many=True, required=False)
    seat_category_mapping = SeatCategoryMappingField(source='*', required=False)
    event = SlugRelatedField(slug_field='slug', read_only=True)
    meta_data = MetaDataField(source='*')
    best_availability_state = serializers.IntegerField(allow_null=True, read_only=True)

    class Meta:
        model = SubEvent
        fields = ('id', 'name', 'date_from', 'date_to', 'active', 'date_admission',
                  'presale_start', 'presale_end', 'location', 'geo_lat', 'geo_lon', 'event', 'is_public',
                  'frontpage_text', 'seating_plan', 'item_price_overrides', 'variation_price_overrides',
                  'meta_data', 'seat_category_mapping', 'last_modified', 'best_availability_state')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.context.get('request') or 'with_availability_for' not in self.context['request'].GET:
            self.fields.pop('best_availability_state')

    def validate(self, data):
        data = super().validate(data)
        event = self.context['request'].event

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        Event.clean_dates(data.get('date_from'), data.get('date_to'))
        Event.clean_presale(data.get('presale_start'), data.get('presale_end'))

        SubEvent.clean_items(event, [item['item'] for item in full_data.get('subeventitem_set', [])])
        SubEvent.clean_variations(event, [item['variation'] for item in full_data.get('subeventitemvariation_set', [])])
        return data

    def validate_item_price_overrides(self, data):
        return list(filter(lambda i: 'item' in i, data))

    def validate_variation_price_overrides(self, data):
        return list(filter(lambda i: 'variation' in i, data))

    def validate_seating_plan(self, value):
        if value and value.organizer != self.context['request'].organizer:
            raise ValidationError('Invalid seating plan.')
        if self.instance and self.instance.pk:
            try:
                validate_plan_change(self.context['request'].event, self.instance, value)
            except SeatProtected as e:
                raise ValidationError(str(e))
        return value

    def validate_seat_category_mapping(self, value):
        item_cache = {i.pk: i for i in self.context['request'].event.items.all()}
        result = {}
        for k, item in value['seat_category_mapping'].items():
            if item not in item_cache:
                raise ValidationError('Item \'{id}\' does not exist.'.format(id=item))
            result[k] = item_cache[item]
        return {'seat_category_mapping': result}

    @cached_property
    def meta_properties(self):
        return {
            p.name: p for p in self.context['request'].organizer.meta_properties.all()
        }

    def validate_meta_data(self, value):
        for key, v in value['meta_data'].items():
            if key not in self.meta_properties:
                raise ValidationError(_('Meta data property \'{name}\' does not exist.').format(name=key))
            if self.meta_properties[key].allowed_values:
                if v not in [_v.strip() for _v in self.meta_properties[key].allowed_values.splitlines()]:
                    raise ValidationError(_('Meta data property \'{name}\' does not allow value \'{value}\'.').format(name=key, value=v))
        return value

    @cached_property
    def ignored_meta_properties(self):
        perm_holder = (self.context['request'].auth if isinstance(self.context['request'].auth, (Device, TeamAPIToken))
                       else self.context['request'].user)
        if perm_holder.has_organizer_permission(self.context['request'].organizer, 'can_change_organizer_settings', request=self.context['request']):
            return []
        return [k for k, p in self.meta_properties.items() if p.protected]

    @transaction.atomic
    def create(self, validated_data):
        item_price_overrides_data = validated_data.pop('subeventitem_set') if 'subeventitem_set' in validated_data else {}
        variation_price_overrides_data = validated_data.pop('subeventitemvariation_set') if 'subeventitemvariation_set' in validated_data else {}
        meta_data = validated_data.pop('meta_data', None)
        seat_category_mapping = validated_data.pop('seat_category_mapping', None)
        subevent = super().create(validated_data)

        for item_price_override_data in item_price_overrides_data:
            SubEventItem.objects.create(subevent=subevent, **item_price_override_data)
        for variation_price_override_data in variation_price_overrides_data:
            SubEventItemVariation.objects.create(subevent=subevent, **variation_price_override_data)

        # Meta data
        if meta_data is not None:
            for key, value in meta_data.items():
                if key not in self.ignored_meta_properties:
                    subevent.meta_values.create(
                        property=self.meta_properties.get(key),
                        value=value
                    )

        # Seats
        if subevent.seating_plan:
            if seat_category_mapping is not None:
                for key, value in seat_category_mapping.items():
                    self.context['request'].event.seat_category_mappings.create(
                        product=value, layout_category=key, subevent=subevent
                    )
            generate_seats(self.context['request'].event, subevent, subevent.seating_plan, {
                m.layout_category: m.product
                for m in self.context['request'].event.seat_category_mappings.select_related('product').filter(subevent=subevent)
            })

        return subevent

    @transaction.atomic
    def update(self, instance, validated_data):
        item_price_overrides_data = validated_data.pop('subeventitem_set', None)
        variation_price_overrides_data = validated_data.pop('subeventitemvariation_set', None)
        meta_data = validated_data.pop('meta_data', None)
        seat_category_mapping = validated_data.pop('seat_category_mapping', None)
        subevent = super().update(instance, validated_data)

        if item_price_overrides_data is not None:
            existing_item_overrides = {item.item: item.id for item in SubEventItem.objects.filter(subevent=subevent)}

            for item_price_override_data in item_price_overrides_data:
                id = existing_item_overrides.pop(item_price_override_data['item'], None)
                SubEventItem(id=id, subevent=subevent, **item_price_override_data).save()

            SubEventItem.objects.filter(id__in=existing_item_overrides.values()).delete()

        if variation_price_overrides_data is not None:
            existing_variation_overrides = {item.variation: item.id for item in SubEventItemVariation.objects.filter(subevent=subevent)}

            for variation_price_override_data in variation_price_overrides_data:
                id = existing_variation_overrides.pop(variation_price_override_data['variation'], None)
                SubEventItemVariation(id=id, subevent=subevent, **variation_price_override_data).save()

            SubEventItemVariation.objects.filter(id__in=existing_variation_overrides.values()).delete()

        # Meta data
        if meta_data is not None:
            current = {mv.property: mv for mv in subevent.meta_values.select_related('property')}
            for key, value in meta_data.items():
                if key not in self.ignored_meta_properties:
                    prop = self.meta_properties.get(key)
                    if prop in current:
                        current[prop].value = value
                        current[prop].save()
                    else:
                        subevent.meta_values.create(
                            property=self.meta_properties.get(key),
                            value=value
                        )

            for prop, current_object in current.items():
                if prop.name not in self.ignored_meta_properties:
                    if prop.name not in meta_data:
                        current_object.delete()

        # Seats
        if seat_category_mapping is not None or ('seating_plan' in validated_data and validated_data['seating_plan'] is None):
            current_mappings = {
                m.layout_category: m
                for m in self.context['request'].event.seat_category_mappings.filter(subevent=subevent)
            }
            if not subevent.seating_plan:
                seat_category_mapping = {}
            for key, value in seat_category_mapping.items():
                if key in current_mappings:
                    m = current_mappings.pop(key)
                    m.product = value
                    m.save()
                else:
                    self.context['request'].event.seat_category_mappings.create(
                        product=value, layout_category=key, subevent=subevent
                    )
            for m in current_mappings.values():
                m.delete()
        if 'seating_plan' in validated_data or seat_category_mapping is not None:
            generate_seats(self.context['request'].event, subevent, subevent.seating_plan, {
                m.layout_category: m.product
                for m in self.context['request'].event.seat_category_mappings.select_related('product').filter(subevent=subevent)
            })

        return subevent


class TaxRuleSerializer(CountryFieldMixin, I18nAwareModelSerializer):
    custom_rules = CompatibleJSONField(
        validators=[CustomRulesValidator()],
        required=False,
        allow_null=True,
    )

    class Meta:
        model = TaxRule
        fields = ('id', 'name', 'rate', 'price_includes_tax', 'eu_reverse_charge', 'home_country', 'internal_name',
                  'keep_gross_if_rate_changes', 'custom_rules')


class EventSettingsSerializer(SettingsSerializer):
    default_fields = [
        'imprint_url',
        'checkout_email_helptext',
        'presale_has_ended_text',
        'voucher_explanation_text',
        'checkout_success_text',
        'banner_text',
        'banner_text_bottom',
        'show_dates_on_frontpage',
        'show_date_to',
        'show_times',
        'show_items_outside_presale_period',
        'display_net_prices',
        'hide_prices_from_attendees',
        'presale_start_show_date',
        'locales',
        'locale',
        'region',
        'last_order_modification_date',
        'allow_modifications_after_checkin',
        'show_quota_left',
        'waiting_list_enabled',
        'waiting_list_hours',
        'waiting_list_auto',
        'waiting_list_names_asked',
        'waiting_list_names_required',
        'waiting_list_phones_asked',
        'waiting_list_phones_required',
        'waiting_list_phones_explanation_text',
        'waiting_list_limit_per_user',
        'max_items_per_order',
        'reservation_time',
        'contact_mail',
        'show_variations_expanded',
        'hide_sold_out',
        'meta_noindex',
        'redirect_to_checkout_directly',
        'frontpage_subevent_ordering',
        'event_list_type',
        'event_list_available_only',
        'event_calendar_future_only',
        'frontpage_text',
        'event_info_text',
        'attendee_names_asked',
        'attendee_names_required',
        'attendee_emails_asked',
        'attendee_emails_required',
        'attendee_addresses_asked',
        'attendee_addresses_required',
        'attendee_company_asked',
        'attendee_company_required',
        'attendee_data_explanation_text',
        'confirm_texts',
        'order_email_asked_twice',
        'order_phone_asked',
        'order_phone_required',
        'checkout_phone_helptext',
        'payment_term_mode',
        'payment_term_days',
        'payment_term_weekdays',
        'payment_term_minutes',
        'payment_term_last',
        'payment_term_expire_automatically',
        'payment_term_expire_delay_days',
        'payment_term_accept_late',
        'payment_explanation',
        'payment_pending_hidden',
        'mail_days_order_expire_warning',
        'ticket_download',
        'ticket_download_date',
        'ticket_download_addons',
        'ticket_download_nonadm',
        'ticket_download_pending',
        'ticket_download_require_validated_email',
        'ticket_secret_length',
        'mail_prefix',
        'mail_from_name',
        'mail_attach_ical',
        'mail_attach_tickets',
        'invoice_address_asked',
        'invoice_address_required',
        'invoice_address_vatid',
        'invoice_address_company_required',
        'invoice_address_beneficiary',
        'invoice_address_custom_field',
        'invoice_name_required',
        'invoice_address_not_asked_free',
        'invoice_show_payments',
        'invoice_reissue_after_modify',
        'invoice_include_free',
        'invoice_generate',
        'invoice_numbers_consecutive',
        'invoice_numbers_prefix',
        'invoice_numbers_prefix_cancellations',
        'invoice_numbers_counter_length',
        'invoice_attendee_name',
        'invoice_event_location',
        'invoice_include_expire_date',
        'invoice_address_explanation_text',
        'invoice_email_attachment',
        'invoice_email_organizer',
        'invoice_address_from_name',
        'invoice_address_from',
        'invoice_address_from_zipcode',
        'invoice_address_from_city',
        'invoice_address_from_country',
        'invoice_address_from_tax_id',
        'invoice_address_from_vat_id',
        'invoice_introductory_text',
        'invoice_additional_text',
        'invoice_footer_text',
        'invoice_eu_currencies',
        'invoice_logo_image',
        'invoice_renderer_highlight_order_code',
        'cancel_allow_user',
        'cancel_allow_user_until',
        'cancel_allow_user_unpaid_keep',
        'cancel_allow_user_unpaid_keep_fees',
        'cancel_allow_user_unpaid_keep_percentage',
        'cancel_allow_user_paid',
        'cancel_allow_user_paid_until',
        'cancel_allow_user_paid_keep',
        'cancel_allow_user_paid_keep_fees',
        'cancel_allow_user_paid_keep_percentage',
        'cancel_allow_user_paid_adjust_fees',
        'cancel_allow_user_paid_adjust_fees_explanation',
        'cancel_allow_user_paid_adjust_fees_step',
        'cancel_allow_user_paid_refund_as_giftcard',
        'cancel_allow_user_paid_require_approval',
        'cancel_allow_user_paid_require_approval_fee_unknown',
        'change_allow_user_variation',
        'change_allow_user_addons',
        'change_allow_user_until',
        'change_allow_user_price',
        'change_allow_attendee',
        'primary_color',
        'theme_color_success',
        'theme_color_danger',
        'theme_color_background',
        'theme_round_borders',
        'primary_font',
        'logo_image',
        'logo_image_large',
        'logo_show_title',
        'og_image',
        'name_scheme',
        'reusable_media_active',
        'reusable_media_type_barcode',
        'reusable_media_type_barcode_identifier_length',
        'reusable_media_type_nfc_uid',
        'reusable_media_type_nfc_uid_autocreate_giftcard',
        'reusable_media_type_nfc_uid_autocreate_giftcard_currency',
        'reusable_media_type_nfc_mf0aes',
        'reusable_media_type_nfc_mf0aes_autocreate_giftcard',
        'reusable_media_type_nfc_mf0aes_autocreate_giftcard_currency',
        'reusable_media_type_nfc_mf0aes_random_uid',
    ]
    readonly_fields = [
        # These are read-only since they are currently only settable on organizers, not events
        'reusable_media_active',
        'reusable_media_type_barcode',
        'reusable_media_type_barcode_identifier_length',
        'reusable_media_type_nfc_uid',
        'reusable_media_type_nfc_uid_autocreate_giftcard',
        'reusable_media_type_nfc_uid_autocreate_giftcard_currency',
        'reusable_media_type_nfc_mf0aes',
        'reusable_media_type_nfc_mf0aes_autocreate_giftcard',
        'reusable_media_type_nfc_mf0aes_autocreate_giftcard_currency',
        'reusable_media_type_nfc_mf0aes_random_uid',
    ]

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        for recv, resp in api_event_settings_fields.send(sender=self.event):
            for fname, field in resp.items():
                field.required = False
                self.fields[fname] = field

    def validate(self, data):
        data = super().validate(data)
        settings_dict = self.instance.freeze()
        settings_dict.update(data)

        if data.get('confirm_texts') is not None:
            data['confirm_texts'] = LazyI18nStringList(data['confirm_texts'])

        validate_event_settings(self.event, settings_dict)
        return data

    def get_new_filename(self, name: str) -> str:
        nonce = get_random_string(length=8)
        fname = '%s/%s/%s.%s.%s' % (
            self.event.organizer.slug, self.event.slug, name.split('/')[-1], nonce, name.split('.')[-1]
        )
        # TODO: make sure pub is always correct
        return 'pub/' + fname


class DeviceEventSettingsSerializer(EventSettingsSerializer):
    default_fields = [
        'locales',
        'locale',
        'last_order_modification_date',
        'show_quota_left',
        'max_items_per_order',
        'attendee_names_asked',
        'attendee_names_required',
        'attendee_emails_asked',
        'attendee_emails_required',
        'attendee_addresses_asked',
        'attendee_addresses_required',
        'attendee_company_asked',
        'attendee_company_required',
        'ticket_download',
        'ticket_download_addons',
        'ticket_download_nonadm',
        'ticket_download_pending',
        'invoice_address_asked',
        'invoice_address_required',
        'invoice_address_vatid',
        'invoice_address_company_required',
        'invoice_address_beneficiary',
        'invoice_address_custom_field',
        'invoice_name_required',
        'invoice_address_not_asked_free',
        'invoice_address_from_name',
        'invoice_address_from',
        'invoice_address_from_zipcode',
        'invoice_address_from_city',
        'invoice_address_from_country',
        'invoice_address_from_tax_id',
        'invoice_address_from_vat_id',
        'name_scheme',
        'reusable_media_type_barcode',
        'reusable_media_type_nfc_uid',
        'reusable_media_type_nfc_mf0aes',
        'reusable_media_type_nfc_mf0aes_random_uid',
        'system_question_order',
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['_name_scheme_fields'] = serializers.JSONField(
            read_only=True,
            default=[{"key": k, "label": str(v), "weight": w} for k, v, w, *__ in PERSON_NAME_SCHEMES.get(self.event.settings.name_scheme)['fields']]
        )
        self.fields['_name_scheme_salutations'] = serializers.JSONField(
            read_only=True,
            default=[{"key": k, "label": str(v)} for k, v in PERSON_NAME_SALUTATIONS]
        )
        self.fields['_name_scheme_titles'] = serializers.JSONField(
            read_only=True,
            default=(
                [{"key": k, "label": k}
                 for k in PERSON_NAME_TITLE_GROUPS.get(self.event.settings.name_scheme_titles)[1]]
                if self.event.settings.name_scheme_titles
                else []
            )
        )


class MultiLineStringField(serializers.Field):

    def to_representation(self, value):
        return [v.strip() for v in value.splitlines()]

    def to_internal_value(self, data):
        if isinstance(data, list) and len(data) > 0:
            return "\n".join(data)
        else:
            raise ValidationError('Invalid data type.')


class ItemMetaPropertiesSerializer(I18nAwareModelSerializer):
    allowed_values = MultiLineStringField(allow_null=True)

    class Meta:
        model = ItemMetaProperty
        fields = ('id', 'name', 'default', 'required', 'allowed_values')
