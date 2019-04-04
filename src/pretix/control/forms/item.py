from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Max
from django.forms.formsets import DELETION_FIELD_NAME
from django.urls import reverse
from django.utils.translation import (
    pgettext_lazy, ugettext as __, ugettext_lazy as _,
)
from i18nfield.forms import I18nFormField, I18nTextarea

from pretix.base.channels import get_all_sales_channels
from pretix.base.forms import I18nFormSet, I18nModelForm
from pretix.base.models import (
    Item, ItemCategory, ItemVariation, Question, QuestionOption, Quota,
)
from pretix.base.models.items import ItemAddOn, ItemBundle
from pretix.base.signals import item_copy_data
from pretix.control.forms import SplitDateTimeField, SplitDateTimePickerWidget
from pretix.control.forms.widgets import Select2
from pretix.helpers.models import modelcopy
from pretix.helpers.money import change_decimal_field


class CategoryForm(I18nModelForm):
    class Meta:
        model = ItemCategory
        localized_fields = '__all__'
        fields = [
            'name',
            'internal_name',
            'description',
            'is_addon'
        ]


class QuestionForm(I18nModelForm):
    question = I18nFormField(
        label=_("Question"),
        widget_kwargs={'attrs': {'rows': 2}},
        widget=I18nTextarea
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['items'].queryset = self.instance.event.items.all()
        self.fields['items'].required = True
        self.fields['dependency_question'].queryset = self.instance.event.questions.filter(
            type__in=(Question.TYPE_BOOLEAN, Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE)
        )
        if self.instance.pk:
            self.fields['dependency_question'].queryset = self.fields['dependency_question'].queryset.exclude(
                pk=self.instance.pk
            )
        self.fields['identifier'].required = False
        self.fields['help_text'].widget.attrs['rows'] = 3

    def clean_dependency_question(self):
        dep = val = self.cleaned_data.get('dependency_question')
        if dep:
            seen_ids = {self.instance.pk} if self.instance else set()
            while dep:
                if dep.pk in seen_ids:
                    raise ValidationError(_('Circular dependency between questions detected.'))
                seen_ids.add(dep.pk)
                dep = dep.dependency_question
        return val

    def clean(self):
        d = super().clean()
        if d.get('dependency_question') and not d.get('dependency_value'):
            raise ValidationError({'dependency_value': [_('This field is required')]})
        if d.get('dependency_question') and d.get('ask_during_checkin'):
            raise ValidationError(_('Dependencies between questions are not supported during check-in.'))
        return d

    class Meta:
        model = Question
        localized_fields = '__all__'
        fields = [
            'question',
            'help_text',
            'type',
            'required',
            'ask_during_checkin',
            'identifier',
            'items',
            'dependency_question',
            'dependency_value'
        ]
        widgets = {
            'items': forms.CheckboxSelectMultiple(
                attrs={'class': 'scrolling-multiple-choice'}
            ),
            'dependency_value': forms.Select,
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
        self.original_instance = modelcopy(self.instance) if self.instance else None
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
                    choices.append(('{}-{}'.format(item.pk, v.pk), '{} – {}'.format(item, v.value)))
            else:
                choices.append(('{}'.format(item.pk), str(item)))

        self.fields['itemvars'] = forms.MultipleChoiceField(
            label=_('Products'),
            required=False,
            choices=choices,
            widget=forms.CheckboxSelectMultiple
        )

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'Date')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
            self.fields['subevent'].required = True
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
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

        self.fields['category'].queryset = self.instance.event.categories.all()
        self.fields['tax_rule'].queryset = self.instance.event.tax_rules.all()
        change_decimal_field(self.fields['default_price'], self.instance.event.currency)
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
            self.instance.free_price = self.cleaned_data['copy_from'].free_price
            self.instance.original_price = self.cleaned_data['copy_from'].original_price
            self.instance.sales_channels = self.cleaned_data['copy_from'].sales_channels
        else:
            # Add to all sales channels by default
            self.instance.sales_channels = [k for k in get_all_sales_channels().keys()]

        self.instance.position = (self.event.items.aggregate(p=Max('position'))['p'] or 0) + 1
        instance = super().save(*args, **kwargs)

        if not self.event.has_subevents and not self.cleaned_data.get('has_variations'):
            if self.cleaned_data.get('quota_option') == self.EXISTING and self.cleaned_data.get('quota_add_existing') is not None:
                quota = self.cleaned_data.get('quota_add_existing')
                quota.items.add(self.instance)
                quota.log_action('pretix.event.quota.changed', user=self.user, data={
                    'item_added': self.instance.pk
                })
            elif self.cleaned_data.get('quota_option') == self.NEW:
                quota_name = self.cleaned_data.get('quota_add_new_name')
                quota_size = self.cleaned_data.get('quota_add_new_size')

                quota = Quota.objects.create(
                    event=self.event, name=quota_name, size=quota_size
                )
                quota.items.add(self.instance)
                quota.log_action('pretix.event.quota.added', user=self.user, data={
                    'name': quota_name,
                    'size': quota_size,
                    'items': [self.instance.pk]
                })

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
            for a in self.cleaned_data['copy_from'].addons.all():
                instance.addons.create(addon_category=a.addon_category, min_count=a.min_count, max_count=a.max_count,
                                       price_included=a.price_included, position=a.position)
            for b in self.cleaned_data['copy_from'].bundles.all():
                instance.bundles.create(bundled_item=b.bundled_item, bundled_variation=b.bundled_variation,
                                        count=b.count, designated_price=b.designated_price)

            item_copy_data.send(sender=self.event, source=self.cleaned_data['copy_from'], target=instance)

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
            'internal_name',
            'category',
            'admission',
            'default_price',
            'tax_rule',
            'allow_cancel'
        ]


class TicketNullBooleanSelect(forms.NullBooleanSelect):
    def __init__(self, attrs=None):
        choices = (
            ('1', _('Choose automatically depending on event settings')),
            ('2', _('Yes, if ticket generation is enabled in general')),
            ('3', _('Never')),
        )
        super(forms.NullBooleanSelect, self).__init__(attrs, choices)


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
        self.fields['description'].widget.attrs['rows'] = '4'
        self.fields['sales_channels'] = forms.MultipleChoiceField(
            label=_('Sales channels'),
            choices=(
                (c.identifier, c.verbose_name) for c in get_all_sales_channels().values()
            ),
            widget=forms.CheckboxSelectMultiple
        )
        change_decimal_field(self.fields['default_price'], self.event.currency)

    class Meta:
        model = Item
        localized_fields = '__all__'
        fields = [
            'category',
            'name',
            'internal_name',
            'active',
            'sales_channels',
            'admission',
            'description',
            'picture',
            'default_price',
            'free_price',
            'tax_rule',
            'available_from',
            'available_until',
            'require_voucher',
            'require_approval',
            'hide_without_voucher',
            'allow_cancel',
            'max_per_order',
            'min_per_order',
            'checkin_attention',
            'generate_tickets',
            'original_price',
            'require_bundling',
        ]
        field_classes = {
            'available_from': SplitDateTimeField,
            'available_until': SplitDateTimeField,
        }
        widgets = {
            'available_from': SplitDateTimePickerWidget(),
            'available_until': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_available_from_0'}),
            'generate_tickets': TicketNullBooleanSelect()
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
                              'currently is in a user\'s cart. Please set the variation as "inactive" instead.'),
                    params=(str(f.instance),)
                )

    def _should_delete_form(self, form):
        should_delete = super()._should_delete_form(form)
        if should_delete and (form.instance.orderposition_set.exists() or form.instance.cartposition_set.exists()):
            form._delete_fail = True
            return False
        return form.cleaned_data.get(DELETION_FIELD_NAME, False)

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        self.is_valid()
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            use_required_attribute=False,
            locales=self.locales,
            event=self.event
        )
        self.add_fields(form, None)
        return form


class ItemVariationForm(I18nModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        change_decimal_field(self.fields['default_price'], self.event.currency)

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
                    try:
                        categories.remove(form.cleaned_data['addon_category'].pk)
                    except KeyError:
                        pass
                    continue

            if 'addon_category' in form.cleaned_data:
                if form.cleaned_data['addon_category'].pk in categories:
                    raise ValidationError(_('You added the same add-on category twice'))

                categories.add(form.cleaned_data['addon_category'].pk)

    @property
    def empty_form(self):
        self.is_valid()
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            use_required_attribute=False,
            locales=self.locales,
            event=self.event
        )
        self.add_fields(form, None)
        return form


class ItemAddOnForm(I18nModelForm):
    def __init__(self, *args, **kwargs):
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


class ItemBundleFormSet(I18nFormSet):
    def __init__(self, *args, **kwargs):
        self.event = kwargs.get('event')
        self.item = kwargs.pop('item')
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        kwargs['item'] = self.item
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        self.is_valid()
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            use_required_attribute=False,
            locales=self.locales,
            item=self.item,
            event=self.event
        )
        self.add_fields(form, None)
        return form


class ItemBundleForm(I18nModelForm):
    itemvar = forms.ChoiceField(label=_('Bundled product'))

    def __init__(self, *args, **kwargs):
        self.item = kwargs.pop('item')
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance', None)
        initial = kwargs.get('initial', {})

        if instance:
            try:
                if instance.bundled_variation:
                    initial['itemvar'] = '%d-%d' % (instance.bundled_item.pk, instance.bundled_variation.pk)
                elif instance.bundled_item:
                    initial['itemvar'] = str(instance.bundled_item.pk)
            except Item.DoesNotExist:
                pass

        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)

        choices = []
        for i in self.event.items.prefetch_related('variations').all():
            pname = str(i)
            if not i.is_available():
                pname += ' ({})'.format(_('inactive'))
            variations = list(i.variations.all())

            if variations:
                for v in variations:
                    choices.append(('%d-%d' % (i.pk, v.pk),
                                    '%s – %s' % (pname, v.value)))
            else:
                choices.append((str(i.pk), '%s' % pname))
        self.fields['itemvar'].choices = choices
        change_decimal_field(self.fields['designated_price'], self.event.currency)

    def clean(self):
        d = super().clean()
        if 'itemvar' in self.cleaned_data:
            if '-' in self.cleaned_data['itemvar']:
                itemid, varid = self.cleaned_data['itemvar'].split('-')
            else:
                itemid, varid = self.cleaned_data['itemvar'], None

            item = Item.objects.get(pk=itemid, event=self.event)
            if varid:
                variation = ItemVariation.objects.get(pk=varid, item=item)
            else:
                variation = None

            if item == self.item:
                raise ValidationError(_("The bundled item must not be the same item as the bundling one."))
            if item.bundles.exists():
                raise ValidationError(_("The bundled item must not have bundles on its own."))

            self.instance.bundled_item = item
            self.instance.bundled_variation = variation

        return d

    class Meta:
        model = ItemBundle
        localized_fields = '__all__'
        fields = [
            'count',
            'designated_price',
        ]
