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


class EventSerializer(I18nAwareModelSerializer):
    class Meta:
        model = Event
        fields = ('name', 'slug', 'live', 'currency', 'date_from',
                  'date_to', 'date_admission', 'is_public', 'presale_start',
                  'presale_end', 'location', 'has_subevents', 'meta_data')

    def validate(self, data):
        data = super().validate(data)

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        Event.clean_dates(data.get('date_from'), data.get('date_to'))
        Event.clean_presale(data.get('presale_start'), data.get('presale_end'))

        return data

    def validate_slug(self, value):
        Event.clean_slug(self.context['request'].organizer, self.instance, value)
        return value

    def validate_live(self, value):
        if value:
            Event.clean_live(self.instance)
        return value


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
