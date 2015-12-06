import copy

from django import forms
from django.db import models
from django.forms import BooleanField
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import I18nModelForm, VersionedModelForm
from pretix.base.models import (
    Item, ItemCategory, ItemVariation, Property, PropertyValue, Question,
    Quota, Versionable,
)
from pretix.control.forms import TolerantFormsetModelForm, VariationsField


class CategoryForm(VersionedModelForm):
    class Meta:
        model = ItemCategory
        localized_fields = '__all__'
        fields = [
            'name'
        ]


class PropertyForm(VersionedModelForm):
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


class QuestionForm(VersionedModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['items'].queryset = self.instance.event.items.current.all()

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
    """
    The form for quotas does not derive from VersionedModelForm as it does not
    perform a 'full clone' as part of a performance optimization
    """

    def __init__(self, **kwargs):
        items = kwargs['items']
        del kwargs['items']
        instance = kwargs.get('instance', None)
        self.original_instance = copy.copy(instance) if instance else None
        super().__init__(**kwargs)

        if hasattr(self, 'instance'):
            active_items = set(self.instance.items.all())
            active_variations = set(self.instance.variations.all())
        else:
            active_items = set()
            active_variations = set()

        for item in items:
            if len(item.properties.all()) > 0:
                self.fields['item_%s' % item.identity] = VariationsField(
                    item, label=_("Activate for"),
                    required=False,
                    initial=active_variations
                )
                self.fields['item_%s' % item.identity].set_item(item)
            else:
                self.fields['item_%s' % item.identity] = BooleanField(
                    label=_("Activate"),
                    required=False,
                    initial=(item in active_items)
                )

    def save(self, commit=True):
        if self.instance.pk is not None and isinstance(self.instance, Versionable):
            if self.has_changed() and self.original_instance:
                new = self.instance
                old = self.original_instance
                clone = old.clone_shallow()
                for f in type(self.instance)._meta.get_fields():
                    if f.name not in (
                            'id', 'identity', 'version_start_date', 'version_end_date',
                            'version_birth_date'
                    ) and not isinstance(f, (
                            models.ManyToOneRel, models.ManyToManyRel, models.ManyToManyField
                    )):
                        setattr(clone, f.name, getattr(new, f.name))
                self.instance = clone
        return super().save(commit)

    class Meta:
        model = Quota
        localized_fields = '__all__'
        fields = [
            'name',
            'size',
        ]


class ItemFormGeneral(VersionedModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = self.instance.event.categories.current.all()

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


class ItemVariationForm(VersionedModelForm):
    class Meta:
        model = ItemVariation
        localized_fields = '__all__'
        fields = [
            'active',
            'default_price',
        ]
