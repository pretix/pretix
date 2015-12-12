import copy

from django import forms
from django.forms import BooleanField
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import I18nModelForm
from pretix.base.models import (
    Item, ItemCategory, ItemVariation, Property, PropertyValue, Question,
    Quota,
)
from pretix.control.forms import TolerantFormsetModelForm, VariationsField


class CategoryForm(I18nModelForm):
    class Meta:
        model = ItemCategory
        localized_fields = '__all__'
        fields = [
            'name'
        ]


class PropertyForm(I18nModelForm):
    class Meta:
        model = Property
        localized_fields = '__all__'
        fields = [
            'name',
        ]


class PropertyValueForm(TolerantFormsetModelForm):
    class Meta:
        model = PropertyValue
        localized_fields = '__all__'
        fields = [
            'value',
        ]


class QuestionForm(I18nModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['items'].queryset = self.instance.event.items.all()

    class Meta:
        model = Question
        localized_fields = '__all__'
        fields = [
            'question',
            'type',
            'required',
            'items'
        ]
        widgets = {
            'items': forms.CheckboxSelectMultiple
        }


class QuotaForm(I18nModelForm):

    def __init__(self, **kwargs):
        items = kwargs['items']
        del kwargs['items']
        instance = kwargs.get('instance', None)
        self.original_instance = copy.copy(instance) if instance else None
        super().__init__(**kwargs)

        if hasattr(self, 'instance') and self.instance.pk:
            active_items = set(self.instance.items.all())
            active_variations = set(self.instance.variations.all())
        else:
            active_items = set()
            active_variations = set()

        for item in items:
            if len(item.properties.all()) > 0:
                self.fields['item_%s' % item.id] = VariationsField(
                    item, label=_("Activate for"),
                    required=False,
                    initial=active_variations
                )
                self.fields['item_%s' % item.id].set_item(item)
            else:
                self.fields['item_%s' % item.id] = BooleanField(
                    label=_("Activate"),
                    required=False,
                    initial=(item in active_items)
                )

    class Meta:
        model = Quota
        localized_fields = '__all__'
        fields = [
            'name',
            'size',
        ]


class ItemFormGeneral(I18nModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = self.instance.event.categories.all()

    class Meta:
        model = Item
        localized_fields = '__all__'
        fields = [
            'category',
            'name',
            'active',
            'admission',
            'description',
            'picture',
            'default_price',
            'tax_rate',
            'available_from',
            'available_until',
        ]


class ItemVariationForm(I18nModelForm):
    class Meta:
        model = ItemVariation
        localized_fields = '__all__'
        fields = [
            'active',
            'default_price',
        ]
