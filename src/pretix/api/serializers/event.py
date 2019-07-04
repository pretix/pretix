from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.functional import cached_property
from django.utils.translation import ugettext as _
from django_countries.serializers import CountryFieldMixin
from rest_framework.fields import Field
from rest_framework.relations import SlugRelatedField

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import Event, TaxRule
from pretix.base.models.event import SubEvent
from pretix.base.models.items import SubEventItem, SubEventItemVariation
from pretix.base.services.seating import (
    SeatProtected, generate_seats, validate_plan_change,
)


class MetaDataField(Field):

    def to_representation(self, value):
        return {
            v.property.name: v.value for v in value.meta_values.all()
        }

    def to_internal_value(self, data):
        return {
            'meta_data': data
        }


class SeatCategoryMappingField(Field):

    def to_representation(self, value):
        qs = value.seat_category_mappings.all()
        if isinstance(value, Event):
            qs = qs.filter(subevent=None)
        return {
            v.layout_category: v.product_id for v in qs
        }

    def to_internal_value(self, data):
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


class EventSerializer(I18nAwareModelSerializer):
    meta_data = MetaDataField(required=False, source='*')
    plugins = PluginsField(required=False, source='*')
    seat_category_mapping = SeatCategoryMappingField(source='*', required=False)

    class Meta:
        model = Event
        fields = ('name', 'slug', 'live', 'testmode', 'currency', 'date_from',
                  'date_to', 'date_admission', 'is_public', 'presale_start',
                  'presale_end', 'location', 'has_subevents', 'meta_data', 'seating_plan',
                  'plugins', 'seat_category_mapping')

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
        for key in value['meta_data'].keys():
            if key not in self.meta_properties:
                raise ValidationError(_('Meta data property \'{name}\' does not exist.').format(name=key))
        return value

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
        if value and value['seat_category_mapping'] and (not self.instance or not self.instance.pk):
            raise ValidationError('You cannot specify seat category mappings on event creation.')
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

    @transaction.atomic
    def create(self, validated_data):
        meta_data = validated_data.pop('meta_data', None)
        validated_data.pop('seat_category_mapping', None)
        plugins = validated_data.pop('plugins', settings.PRETIX_PLUGINS_DEFAULT.split(','))
        event = super().create(validated_data)

        # Meta data
        if meta_data is not None:
            for key, value in meta_data.items():
                event.meta_values.create(
                    property=self.meta_properties.get(key),
                    value=value
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
        plugins = validated_data.pop('plugins', None)
        seat_category_mapping = validated_data.pop('seat_category_mapping', None)
        event = super().update(instance, validated_data)

        # Meta data
        if meta_data is not None:
            current = {mv.property: mv for mv in event.meta_values.select_related('property')}
            for key, value in meta_data.items():
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
                if prop.name not in meta_data:
                    current_object.delete()

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
        new_event = super().create(validated_data)

        event = Event.objects.filter(slug=self.context['event'], organizer=self.context['organizer'].pk).first()
        new_event.copy_data_from(event)

        if plugins is not None:
            new_event.set_active_plugins(plugins)
        if is_public is not None:
            new_event.is_public = is_public
        if testmode is not None:
            new_event.testmode = testmode
        new_event.save()

        return new_event


class SubEventItemSerializer(I18nAwareModelSerializer):
    class Meta:
        model = SubEventItem
        fields = ('item', 'price')


class SubEventItemVariationSerializer(I18nAwareModelSerializer):
    class Meta:
        model = SubEventItemVariation
        fields = ('variation', 'price')


class SubEventSerializer(I18nAwareModelSerializer):
    item_price_overrides = SubEventItemSerializer(source='subeventitem_set', many=True, required=False)
    variation_price_overrides = SubEventItemVariationSerializer(source='subeventitemvariation_set', many=True, required=False)
    seat_category_mapping = SeatCategoryMappingField(source='*', required=False)
    event = SlugRelatedField(slug_field='slug', read_only=True)
    meta_data = MetaDataField(source='*')

    class Meta:
        model = SubEvent
        fields = ('id', 'name', 'date_from', 'date_to', 'active', 'date_admission',
                  'presale_start', 'presale_end', 'location', 'event', 'is_public', 'seating_plan',
                  'item_price_overrides', 'variation_price_overrides', 'meta_data', 'seat_category_mapping')

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
        for key in value['meta_data'].keys():
            if key not in self.meta_properties:
                raise ValidationError(_('Meta data property \'{name}\' does not exist.').format(name=key))
        return value

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
        item_price_overrides_data = validated_data.pop('subeventitem_set') if 'subeventitem_set' in validated_data else {}
        variation_price_overrides_data = validated_data.pop('subeventitemvariation_set') if 'subeventitemvariation_set' in validated_data else {}
        meta_data = validated_data.pop('meta_data', None)
        seat_category_mapping = validated_data.pop('seat_category_mapping', None)
        subevent = super().update(instance, validated_data)

        existing_item_overrides = {item.item: item.id for item in SubEventItem.objects.filter(subevent=subevent)}

        for item_price_override_data in item_price_overrides_data:
            id = existing_item_overrides.pop(item_price_override_data['item'], None)
            SubEventItem(id=id, subevent=subevent, **item_price_override_data).save()

        SubEventItem.objects.filter(id__in=existing_item_overrides.values()).delete()

        existing_variation_overrides = {item.variation: item.id for item in SubEventItemVariation.objects.filter(subevent=subevent)}

        for variation_price_override_data in variation_price_overrides_data:
            id = existing_variation_overrides.pop(variation_price_override_data['variation'], None)
            SubEventItemVariation(id=id, subevent=subevent, **variation_price_override_data).save()

        SubEventItemVariation.objects.filter(id__in=existing_variation_overrides.values()).delete()

        # Meta data
        if meta_data is not None:
            current = {mv.property: mv for mv in subevent.meta_values.select_related('property')}
            for key, value in meta_data.items():
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
    class Meta:
        model = TaxRule
        fields = ('id', 'name', 'rate', 'price_includes_tax', 'eu_reverse_charge', 'home_country')
