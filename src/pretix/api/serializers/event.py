from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.functional import cached_property
from django.utils.translation import ugettext as _
from django_countries.serializers import CountryFieldMixin
from rest_framework.fields import Field

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import Event, TaxRule
from pretix.base.models.event import SubEvent
from pretix.base.models.items import SubEventItem, SubEventItemVariation


class MetaDataField(Field):

    def to_representation(self, value):
        return {
            v.property.name: v.value for v in value.meta_values.all()
        }

    def to_internal_value(self, data):
        return {
            'meta_data': data
        }


class PluginsField(Field):

    def to_representation(self, obj):
        from pretix.base.plugins import get_all_plugins

        plugins = {
            p.module for p in get_all_plugins()
            if not p.name.startswith('.') and getattr(p, 'visible', True) and p.module in obj.get_plugins()
        }

        return plugins

    def to_internal_value(self, data):
        from pretix.base.plugins import get_all_plugins

        plugins_available = {
            p.module for p in get_all_plugins()
            if not p.name.startswith('.') and getattr(p, 'visible', True)
        }

        for plugin in data:
            if plugin not in plugins_available:
                raise ValidationError(
                    message=_("Unknown plugin: '%s'."),
                    params=(plugin,)
                )
                break

        plugins = {plugin_name for plugin_name in data}

        return {
            'plugins': ",".join(plugins)
        }


class EventSerializer(I18nAwareModelSerializer):
    meta_data = MetaDataField(required=False, source='*')
    plugins = PluginsField(required=False, source='*')

    class Meta:
        model = Event
        fields = ('name', 'slug', 'live', 'currency', 'date_from',
                  'date_to', 'date_admission', 'is_public', 'presale_start',
                  'presale_end', 'location', 'has_subevents', 'meta_data', 'plugins')

    def validate(self, data):
        data = super().validate(data)

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        Event.clean_dates(data.get('date_from'), data.get('date_to'))
        Event.clean_presale(data.get('presale_start'), data.get('presale_end'))

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

    @transaction.atomic
    def create(self, validated_data):
        meta_data = validated_data.pop('meta_data', None)
        event = super().create(validated_data)

        # Meta data
        if meta_data is not None:
            for key, value in meta_data.items():
                event.meta_values.create(
                    property=self.meta_properties.get(key),
                    value=value
                )
        return event

    @transaction.atomic
    def update(self, instance, validated_data):
        meta_data = validated_data.pop('meta_data', None)
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

        return event


class SubEventItemSerializer(I18nAwareModelSerializer):
    class Meta:
        model = SubEventItem
        fields = ('item', 'price')


class SubEventItemVariationSerializer(I18nAwareModelSerializer):
    class Meta:
        model = SubEventItemVariation
        fields = ('variation', 'price')


class SubEventSerializer(I18nAwareModelSerializer):
    item_price_overrides = SubEventItemSerializer(source='subeventitem_set', many=True)
    variation_price_overrides = SubEventItemVariationSerializer(source='subeventitemvariation_set', many=True)
    meta_data = MetaDataField(source='*')

    class Meta:
        model = SubEvent
        fields = ('id', 'name', 'date_from', 'date_to', 'active', 'date_admission',
                  'presale_start', 'presale_end', 'location',
                  'item_price_overrides', 'variation_price_overrides', 'meta_data')


class TaxRuleSerializer(CountryFieldMixin, I18nAwareModelSerializer):
    class Meta:
        model = TaxRule
        fields = ('id', 'name', 'rate', 'price_includes_tax', 'eu_reverse_charge', 'home_country')
