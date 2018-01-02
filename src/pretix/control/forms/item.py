import copy

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Max
from django.forms.formsets import DELETION_FIELD_NAME
from django.utils.translation import ugettext as __, ugettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextarea

from pretix.base.forms import I18nFormSet, I18nModelForm
from pretix.base.models import (
    Item, ItemCategory, ItemVariation, Question, QuestionOption, Quota,
)
from pretix.base.models.items import ItemAddOn
from pretix.control.forms import SplitDateTimePickerWidget


class CategoryForm(I18nModelForm):
    class Meta:
        model = ItemCategory
        localized_fields = '__all__'
        fields = [
            'name',
            'description',
            'is_addon'
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
            'help_text',
            'type',
            'required',
            'items'
        ]
        widgets = {
            'items': forms.CheckboxSelectMultiple(
                attrs={'class': 'scrolling-multiple-choice'}
            ),
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
        self.instance = kwargs.get('instance', None)
        self.event = kwargs.get('event')
        items = kwargs.pop('items', None) or self.event.items.prefetch_related('variations')
        self.original_instance = copy.copy(self.instance) if self.instance else None
        initial = kwargs.get('initial', {})
        if self.instance and self.instance.pk:
            initial['itemvars'] = [str(i.pk) for i in self.instance.items.all()] + [
                '{}-{}'.format(v.item_id, v.pk) for v in self.instance.variations.all()
            ]
        kwargs['initial'] = initial
        super().__init__(**kwargs)

        choices = []
        for item in items:
            if len(item.variations.all()) > 0:
                for v in item.variations.all():
                    choices.append(('{}-{}'.format(item.pk, v.pk), '{} – {}'.format(item.name, v.value)))
            else:
                choices.append(('{}'.format(item.pk), item.name))

        self.fields['itemvars'] = forms.MultipleChoiceField(
            label=_('Products'),
            required=False,
            choices=choices,
            widget=forms.CheckboxSelectMultiple
        )

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
        else:
            del self.fields['subevent']

    class Meta:
        model = Quota
        localized_fields = '__all__'
        fields = [
            'name',
            'size',
            'subevent'
        ]

    def save(self, *args, **kwargs):
        creating = not self.instance.pk
        inst = super().save(*args, **kwargs)

        selected_items = set(list(self.event.items.filter(id__in=[
            i.split('-')[0] for i in self.cleaned_data['itemvars']
        ])))
        selected_variations = list(ItemVariation.objects.filter(item__event=self.event, id__in=[
            i.split('-')[1] for i in self.cleaned_data['itemvars'] if '-' in i
        ]))

        current_items = [] if creating else self.instance.items.all()
        current_variations = [] if creating else self.instance.variations.all()

        self.instance.items.remove(*[i for i in current_items if i not in selected_items])
        self.instance.items.add(*[i for i in selected_items if i not in current_items])
        self.instance.variations.remove(*[i for i in current_variations if i not in selected_variations])
        self.instance.variations.add(*[i for i in selected_variations if i not in current_variations])
        return inst


class ItemCreateForm(I18nModelForm):
    NONE = 'none'
    EXISTING = 'existing'
    NEW = 'new'
    has_variations = forms.BooleanField(label=_('The product should exist in multiple variations'),
                                        help_text=_('Select this option e.g. for t-shirts that come in multiple sizes. '
                                                    'You can select the variations in the next step.'),
                                        required=False)

    def __init__(self, *args, **kwargs):
        self.event = kwargs['event']
        super().__init__(*args, **kwargs)

        self.fields['category'].queryset = self.instance.event.categories.all()
        self.fields['tax_rule'].queryset = self.instance.event.tax_rules.all()
        self.fields['tax_rule'].empty_label = _('No taxation')
        self.fields['copy_from'] = forms.ModelChoiceField(
            label=_("Copy product information"),
            queryset=self.event.items.all(),
            widget=forms.Select,
            empty_label=_('Do not copy'),
            required=False
        )

        if not self.event.has_subevents:
            choices = [
                (self.NONE, _("Do not add to a quota now")),
                (self.EXISTING, _("Add product to an existing quota")),
                (self.NEW, _("Create a new quota for this product"))
            ]
            if not self.event.quotas.exists():
                choices.remove(choices[1])

            self.fields['quota_option'] = forms.ChoiceField(
                label=_("Quota options"),
                widget=forms.RadioSelect,
                choices=choices,
                initial=self.NONE,
                required=False
            )

            self.fields['quota_add_existing'] = forms.ModelChoiceField(
                label=_("Add to existing quota"),
                widget=forms.Select(),
                queryset=self.instance.event.quotas.all(),
                required=False
            )

            self.fields['quota_add_new_name'] = forms.CharField(
                label=_("Name"),
                max_length=200,
                widget=forms.TextInput(attrs={'placeholder': _("New quota name")}),
                required=False
            )

            self.fields['quota_add_new_size'] = forms.IntegerField(
                min_value=0,
                label=_("Size"),
                widget=forms.TextInput(attrs={'placeholder': _("Number of tickets")}),
                help_text=_("Leave empty for an unlimited number of tickets."),
                required=False
            )

    def save(self, *args, **kwargs):
        if self.cleaned_data.get('copy_from'):
            self.instance.description = self.cleaned_data['copy_from'].description
            self.instance.active = self.cleaned_data['copy_from'].active
            self.instance.available_from = self.cleaned_data['copy_from'].available_from
            self.instance.available_until = self.cleaned_data['copy_from'].available_until
            self.instance.require_voucher = self.cleaned_data['copy_from'].require_voucher
            self.instance.hide_without_voucher = self.cleaned_data['copy_from'].hide_without_voucher
            self.instance.allow_cancel = self.cleaned_data['copy_from'].allow_cancel
            self.instance.min_per_order = self.cleaned_data['copy_from'].min_per_order
            self.instance.max_per_order = self.cleaned_data['copy_from'].max_per_order
            self.instance.checkin_attention = self.cleaned_data['copy_from'].checkin_attention

        self.instance.position = (self.event.items.aggregate(p=Max('position'))['p'] or 0) + 1
        instance = super().save(*args, **kwargs)

        if not self.event.has_subevents and not self.cleaned_data.get('has_variations'):
            if self.cleaned_data.get('quota_option') == self.EXISTING and self.cleaned_data.get('quota_add_existing') is not None:
                quota = self.cleaned_data.get('quota_add_existing')
                quota.items.add(self.instance)
            elif self.cleaned_data.get('quota_option') == self.NEW:
                quota_name = self.cleaned_data.get('quota_add_new_name')
                quota_size = self.cleaned_data.get('quota_add_new_size')

                quota = Quota.objects.create(
                    event=self.event, name=quota_name, size=quota_size
                )
                quota.items.add(self.instance)

        if self.cleaned_data.get('has_variations'):
            if self.cleaned_data.get('copy_from') and self.cleaned_data.get('copy_from').has_variations:
                for variation in self.cleaned_data['copy_from'].variations.all():
                    ItemVariation.objects.create(item=instance, value=variation.value, active=variation.active,
                                                 position=variation.position, default_price=variation.default_price)
            else:
                ItemVariation.objects.create(
                    item=instance, value=__('Standard')
                )

        if self.cleaned_data.get('copy_from'):
            for question in self.cleaned_data['copy_from'].questions.all():
                question.items.add(instance)

        return instance

    def clean(self):
        cleaned_data = super().clean()

        if not self.event.has_subevents:
            if cleaned_data.get('quota_option') == self.NEW:
                if not self.cleaned_data.get('quota_add_new_name'):
                    raise forms.ValidationError(
                        {'quota_add_new_name': [_("Quota name is required.")]}
                    )
            elif cleaned_data.get('quota_option') == self.EXISTING:
                if not self.cleaned_data.get('quota_add_existing'):
                    raise forms.ValidationError(
                        {'quota_add_existing': [_("Please select a quota.")]}
                    )

        return cleaned_data

    class Meta:
        model = Item
        localized_fields = '__all__'
        fields = [
            'name',
            'category',
            'admission',
            'default_price',
            'tax_rule',
            'allow_cancel'
        ]


class ItemUpdateForm(I18nModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = self.instance.event.categories.all()
        self.fields['tax_rule'].queryset = self.instance.event.tax_rules.all()
        self.fields['description'].widget.attrs['placeholder'] = _(
            'e.g. This reduced price is available for full-time students, jobless and people '
            'over 65. This ticket includes access to all parts of the event, except the VIP '
            'area.'
        )

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
            'tax_rule',
            'available_from',
            'available_until',
            'require_voucher',
            'hide_without_voucher',
            'allow_cancel',
            'max_per_order',
            'min_per_order',
            'checkin_attention'
        ]
        field_classes = {
            'available_from': forms.SplitDateTimeField,
            'available_until': forms.SplitDateTimeField,
        }
        widgets = {
            'available_from': SplitDateTimePickerWidget(),
            'available_until': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_available_from_0'}),
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
            'description',
        ]


class ItemAddOnsFormSet(I18nFormSet):
    def __init__(self, *args, **kwargs):
        self.event = kwargs.get('event')
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        return super()._construct_form(i, **kwargs)

    def clean(self):
        super().clean()
        categories = set()
        for i in range(0, self.total_form_count()):
            form = self.forms[i]
            if self.can_delete:
                if self._should_delete_form(form):
                    # This form is going to be deleted so any of its errors
                    # should not cause the entire formset to be invalid.
                    continue

            if form.cleaned_data['addon_category'] in categories:
                raise ValidationError(_('You added the same add-on category twice'))

            categories.add(form.cleaned_data['addon_category'])

    @property
    def empty_form(self):
        self.is_valid()
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            locales=self.locales,
            event=self.event
        )
        self.add_fields(form, None)
        return form


class ItemAddOnForm(I18nModelForm):
    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['addon_category'].queryset = self.event.categories.all()

    class Meta:
        model = ItemAddOn
        localized_fields = '__all__'
        fields = [
            'addon_category',
            'min_count',
            'max_count',
            'price_included'
        ]
        help_texts = {
            'min_count': _('Be aware that setting a minimal number makes it impossible to buy this product if all '
                           'available add-ons are sold out.')
        }
