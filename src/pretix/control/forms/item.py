from django.forms import BooleanField
from django.utils.translation import ugettext_lazy as _
from pretix.base.forms import VersionedModelForm, I18nModelForm
from pretix.base.models import (
    Item, ItemCategory, Property, ItemVariation, PropertyValue, Question, Quota,
    Versionable)
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
    class Meta:
        model = Question
        localized_fields = '__all__'
        fields = [
            'question',
            'type',
            'required',
        ]


class QuotaForm(I18nModelForm):
    def __init__(self, **kwargs):
        items = kwargs['items']
        del kwargs['items']
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
            if self.has_changed():
                self.instance = self.instance.clone_shallow()
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
        self.fields['properties'].queryset = self.instance.event.properties.current.all()
        self.fields['questions'].queryset = self.instance.event.questions.current.all()

    class Meta:
        model = Item
        localized_fields = '__all__'
        fields = [
            'category',
            'name',
            'active',
            'admission',
            'short_description',
            'long_description',
            'default_price',
            'tax_rate',
            'properties',
            'questions',
        ]


class ItemVariationForm(VersionedModelForm):
    class Meta:
        model = ItemVariation
        localized_fields = '__all__'
        fields = [
            'active',
            'default_price',
        ]
