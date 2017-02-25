import copy

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BooleanField, ModelMultipleChoiceField
from django.forms.formsets import DELETION_FIELD_NAME
from django.utils.translation import ugettext as __, ugettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextarea

from pretix.base.forms import I18nFormSet, I18nModelForm
from pretix.base.models import (
    Item, ItemCategory, ItemVariation, Question, QuestionOption, Quota,
)


class CategoryForm(I18nModelForm):
    class Meta:
        model = ItemCategory
        localized_fields = '__all__'
        fields = [
            'name',
            'description'
        ]


class QuestionForm(I18nModelForm):
    question = I18nFormField(
        label=_("Question"),
        widget_kwargs={'attrs': {'rows': 5}},
        widget=I18nTextarea
    )

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
            'items': forms.CheckboxSelectMultiple,
        }


class QuestionOptionForm(I18nModelForm):

    class Meta:
        model = QuestionOption
        localized_fields = '__all__'
        fields = [
            'answer',
        ]


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
            if len(item.variations.all()) > 0:
                self.fields['item_%s' % item.id] = ModelMultipleChoiceField(
                    label=_("Activate for"),
                    required=False,
                    initial=active_variations,
                    queryset=item.variations.all(),
                    widget=forms.CheckboxSelectMultiple
                )
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


class ItemCreateForm(I18nModelForm):
    has_variations = forms.BooleanField(label=_('The product should exist in multiple variations'),
                                        help_text=_('Select this option e.g. for t-shirts that come in multiple sizes. '
                                                    'You can select the variations in the next step.'),
                                        required=False)

    def __init__(self, *args, **kwargs):
        self.event = kwargs['event']
        super().__init__(*args, **kwargs)
        self.fields['copy_from'] = forms.ModelChoiceField(
            label=_("Copy product information"),
            queryset=self.event.items.all(),
            widget=forms.Select,
            empty_label=_('Do not copy'),
            required=False
        )

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        if self.cleaned_data.get('has_variations'):
            if self.cleaned_data.get('copy_from') and self.cleaned_data.get('copy_from').has_variations:
                for variation in self.cleaned_data['copy_from'].variations.all():
                    ItemVariation.objects.create(item=instance, value=variation.value, active=variation.active,
                                                 position=variation.position, default_price=variation.default_price)
            else:
                ItemVariation.objects.create(
                    item=instance, value=__('Standard')
                )

        for question in Question.objects.filter(items=self.cleaned_data.get('copy_from')):
            question.items.add(instance)

        return instance

    class Meta:
        model = Item
        localized_fields = '__all__'
        fields = [
            'name',
            'admission',
            'default_price',
            'tax_rate',
            'allow_cancel'
        ]


class ItemUpdateForm(I18nModelForm):
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
            'free_price',
            'tax_rate',
            'available_from',
            'available_until',
            'require_voucher',
            'hide_without_voucher',
            'allow_cancel'
        ]
        widgets = {
            'available_from': forms.DateTimeInput(attrs={'class': 'datetimepicker'}),
            'available_until': forms.DateTimeInput(attrs={'class': 'datetimepicker'}),
        }


class ItemVariationsFormSet(I18nFormSet):

    def clean(self):
        super().clean()
        for f in self.forms:
            if hasattr(f, '_delete_fail'):
                f.fields['DELETE'].initial = False
                f.fields['DELETE'].disabled = True
                raise ValidationError(
                    message=_('The variation "%s" cannot be deleted because it has already been ordered by a user or '
                              'currently is in a users\'s cart. Please set the variation as "inactive" instead.'),
                    params=(str(f.instance),)
                )

    def _should_delete_form(self, form):
        should_delete = super()._should_delete_form(form)
        if should_delete and (form.instance.orderposition_set.exists() or form.instance.cartposition_set.exists()):
            form._delete_fail = True
            return False
        return form.cleaned_data.get(DELETION_FIELD_NAME, False)


class ItemVariationForm(I18nModelForm):
    class Meta:
        model = ItemVariation
        localized_fields = '__all__'
        fields = [
            'value',
            'active',
            'default_price',
        ]
