#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
# This file contains Apache-licensed contributions copyrighted by: Adam K. Sumner, Clint, Enrique Saez, Jakob Schnell,
# Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import copy
import os
from decimal import Decimal
from urllib.parse import urlencode

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Max, Q
from django.forms import ChoiceField, RadioSelect
from django.forms.formsets import DELETION_FIELD_NAME
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as __, gettext_lazy as _
from django_scopes.forms import (
    SafeModelChoiceField, SafeModelMultipleChoiceField,
)
from i18nfield.forms import I18nFormField, I18nTextarea

from pretix.base.forms import I18nFormSet, I18nMarkdownTextarea, I18nModelForm
from pretix.base.forms.widgets import DatePickerWidget
from pretix.base.models import (
    Item, ItemCategory, ItemProgramTime, ItemVariation, Question,
    QuestionOption, Quota,
)
from pretix.base.models.items import ItemAddOn, ItemBundle, ItemMetaValue
from pretix.base.signals import item_copy_data
from pretix.control.forms import (
    ButtonGroupRadioSelect, ExtFileField, ItemMultipleChoiceField,
    SalesChannelCheckboxSelectMultiple, SplitDateTimeField,
    SplitDateTimePickerWidget,
)
from pretix.control.forms.widgets import Select2, Select2ItemVarMulti
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
            'cross_selling_condition',
            'cross_selling_match_products',
        ]
        widgets = {
            'description': I18nMarkdownTextarea,
            'cross_selling_condition': RadioSelect,
        }
        field_classes = {
            'cross_selling_match_products': SafeModelMultipleChoiceField,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tpl = '{} &nbsp; <span class="text-muted">{}</span>'
        self.fields['category_type'] = ChoiceField(widget=RadioSelect, choices=(
            ('normal', mark_safe(tpl.format(
                _('Normal category'),
                _('Products in this category are regular products displayed on the front page.')
            )),),
            ('addon', mark_safe(tpl.format(
                _('Add-on product category'),
                _('Products in this category are add-on products and can only be bought as add-ons.')
            )),),
            ('only', mark_safe(tpl.format(
                _('Cross-selling category'),
                _('Products in this category are regular products, but are only shown in the cross-selling step, '
                  'according to the configuration below.')
            )),),
            ('both', mark_safe(tpl.format(
                _('Normal + cross-selling category'),
                _('Products in this category are regular products displayed on the front page, but are additionally '
                  'shown in the cross-selling step, according to the configuration below.')
            )),),
        ))
        self.fields['category_type'].initial = self.instance.category_type

        self.fields['cross_selling_condition'].widget.attrs['data-display-dependency'] = '#id_category_type_2,#id_category_type_3'
        self.fields['cross_selling_condition'].widget.attrs['data-disable-dependent'] = 'true'
        self.fields['cross_selling_condition'].widget.choices = self.fields['cross_selling_condition'].widget.choices[1:]
        self.fields['cross_selling_condition'].required = False
        self.fields['cross_selling_condition']._required = True  # Do not display "Optional" label

        self.fields['cross_selling_match_products'].widget = forms.CheckboxSelectMultiple(
            attrs={
                'class': 'scrolling-multiple-choice',
                'data-display-dependency': '#id_cross_selling_condition_2'
            }
        )
        self.fields['cross_selling_match_products'].queryset = self.event.items.filter(
            # don't show products which are only visible in addon/cross-sell step themselves
            Q(category__isnull=True) | Q(
                Q(category__is_addon=False) & Q(Q(category__cross_selling_mode='both') | Q(category__cross_selling_mode__isnull=True))
            )
        )

    def clean(self):
        d = super().clean()
        if d.get('category_type') == 'only' or d.get('category_type') == 'both':
            if not d.get('cross_selling_condition'):
                raise ValidationError({'cross_selling_condition': [_('This field is required')]})
        self.instance.category_type = d.get('category_type')
        return d


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
            type__in=(Question.TYPE_BOOLEAN, Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE),
            ask_during_checkin=False
        )
        if self.instance.pk:
            self.fields['dependency_question'].queryset = self.fields['dependency_question'].queryset.exclude(
                pk=self.instance.pk
            )
        self.fields['identifier'].required = False
        self.fields['dependency_values'].required = False
        self.fields['help_text'].widget.attrs['rows'] = 3

    def clean_dependency_values(self):
        val = self.data.getlist('dependency_values')
        return val

    def clean_dependency_question(self):
        dep = val = self.cleaned_data.get('dependency_question')
        if dep:
            if dep.ask_during_checkin:
                raise ValidationError(_('Question cannot depend on a question asked during check-in.'))

            seen_ids = {self.instance.pk} if self.instance else set()
            while dep:
                if dep.pk in seen_ids:
                    raise ValidationError(_('Circular dependency between questions detected.'))
                seen_ids.add(dep.pk)
                dep = dep.dependency_question
        return val

    def clean_ask_during_checkin(self):
        val = self.cleaned_data.get('ask_during_checkin')

        if val and self.cleaned_data.get('type') in Question.ASK_DURING_CHECKIN_UNSUPPORTED:
            raise ValidationError(_('This type of question cannot be asked during check-in.'))

        return val

    def clean_show_during_checkin(self):
        val = self.cleaned_data.get('show_during_checkin')

        if val and self.cleaned_data.get('type') in Question.SHOW_DURING_CHECKIN_UNSUPPORTED:
            raise ValidationError(_('This type of question cannot be shown during check-in.'))

        return val

    def clean_type(self):
        val = self.cleaned_data.get('type')
        if self.instance:
            self.instance.clean_type_change(self.instance.type, val)
        return val

    def clean_identifier(self):
        val = self.cleaned_data.get('identifier')
        Question._clean_identifier(self.instance.event, val, self.instance)
        return val

    def clean(self):
        d = super().clean()
        if d.get('dependency_question') and not d.get('dependency_values'):
            raise ValidationError({'dependency_values': [_('This field is required')]})
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
            'show_during_checkin',
            'hidden',
            'identifier',
            'items',
            'dependency_question',
            'dependency_values',
            'print_on_invoice',
            'valid_number_min',
            'valid_number_max',
            'valid_datetime_min',
            'valid_datetime_max',
            'valid_date_min',
            'valid_date_max',
            'valid_file_portrait',
            'valid_string_length_max',
        ]
        widgets = {
            'valid_datetime_min': SplitDateTimePickerWidget(),
            'valid_datetime_max': SplitDateTimePickerWidget(),
            'valid_date_min': DatePickerWidget(),
            'valid_date_max': DatePickerWidget(),
            'items': forms.CheckboxSelectMultiple(
                attrs={'class': 'scrolling-multiple-choice'}
            ),
            'dependency_values': forms.SelectMultiple,
            'help_text': I18nMarkdownTextarea,
        }
        field_classes = {
            'valid_datetime_min': SplitDateTimeField,
            'valid_datetime_max': SplitDateTimeField,
            'items': ItemMultipleChoiceField,
            'dependency_question': SafeModelChoiceField,
        }


class QuestionOptionForm(I18nModelForm):
    class Meta:
        model = QuestionOption
        localized_fields = '__all__'
        fields = [
            'answer',
        ]


class QuotaForm(I18nModelForm):
    itemvars = forms.MultipleChoiceField(
        label=_("Products"),
        required=True,
    )

    def __init__(self, **kwargs):
        self.instance = kwargs.get('instance', None)
        self.event = kwargs.get('event')
        items = kwargs.pop('items', None) or self.event.items.prefetch_related('variations')
        searchable_selection = kwargs.pop('searchable_selection', None)
        self.original_instance = modelcopy(self.instance) if self.instance else None
        initial = kwargs.get('initial', {})
        if self.instance and self.instance.pk and 'itemvars' not in initial:
            initial['itemvars'] = [str(i.pk) for i in self.instance.items.all() if (len(i.variations.all()) == 0)] + [
                '{}-{}'.format(v.item_id, v.pk) for v in self.instance.variations.all()
            ]
        kwargs['initial'] = initial
        super().__init__(**kwargs)

        choices = []
        for item in items:
            if len(item.variations.all()) > 0:
                for v in item.variations.all():
                    choices.append((
                        '{}-{}'.format(item.pk, v.pk),
                        '{} – {}'.format(item, v.value) if item.active else mark_safe(f'<strike class="text-muted">{escape(item)} – {escape(v.value)}</strike>')
                    ))
            else:
                choices.append(('{}'.format(item.pk), str(item) if item.active else mark_safe(f'<strike class="text-muted">{escape(item)}</strike>')))

        if searchable_selection:
            self.fields['itemvars'].widget = Select2ItemVarMulti(
                attrs={
                    'data-model-select2': 'generic',
                    'data-select2-url': reverse('control:event.items.itemvars.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                    'data-placeholder': _('No products')
                },
                choices=choices,
            )
        else:
            self.fields['itemvars'].widget = forms.CheckboxSelectMultiple()

        self.fields['itemvars'].choices = choices

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
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
            'subevent',
            'close_when_sold_out',
            'release_after_exit',
            'ignore_for_event_availability',
        ]
        field_classes = {
            'subevent': SafeModelChoiceField,
        }
        widgets = {
            'size': forms.NumberInput(attrs={'placeholder': _('Unlimited')})
        }

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
        kwargs.setdefault('initial', {})
        kwargs['initial'].setdefault('admission', True)
        kwargs['initial'].setdefault('personalized', True)
        super().__init__(*args, **kwargs)

        self.fields['category'].queryset = self.instance.event.categories.all()
        self.fields['category'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.items.categories.select2', kwargs={
                    'event': self.instance.event.slug,
                    'organizer': self.instance.event.organizer.slug,
                }),
                'data-placeholder': _('No category'),
            }
        )
        self.fields['category'].widget.choices = self.fields['category'].choices

        self.fields['tax_rule'].queryset = self.instance.event.tax_rules.all()
        change_decimal_field(self.fields['default_price'], self.instance.event.currency)
        self.fields['copy_from'] = forms.ModelChoiceField(
            label=_("Copy product information"),
            queryset=self.event.items.all(),
            widget=forms.Select,
            empty_label=_('Do not copy'),
            required=False
        )
        if self.event.tax_rules.exists():
            self.fields['tax_rule'].required = True
        else:
            self.fields['tax_rule'].empty_label = _('No taxation')

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
            src = self.cleaned_data['copy_from']
            fields = (
                'description',
                'active',
                'available_from',
                'available_from_mode',
                'available_until',
                'available_until_mode',
                'require_voucher',
                'hide_without_voucher',
                'allow_cancel',
                'min_per_order',
                'max_per_order',
                'generate_tickets',
                'checkin_attention',
                'checkin_text',
                'free_price',
                'original_price',
                'all_sales_channels',
                'issue_giftcard',
                'require_approval',
                'allow_waitinglist',
                'show_quota_left',
                'hidden_if_available',
                'hidden_if_item_available',
                'hidden_if_item_available_mode',
                'require_bundling',
                'require_membership',
                'grant_membership_type',
                'grant_membership_duration_like_event',
                'grant_membership_duration_days',
                'grant_membership_duration_months',
                'validity_mode',
                'validity_fixed_from',
                'validity_fixed_until',
                'validity_dynamic_duration_minutes',
                'validity_dynamic_duration_hours',
                'validity_dynamic_duration_days',
                'validity_dynamic_duration_months',
                'validity_dynamic_start_choice',
                'validity_dynamic_start_choice_day_limit',
                'media_type',
                'media_policy',
            )
            for f in fields:
                setattr(self.instance, f, getattr(src, f))

            if src.picture:
                self.instance.picture.save(os.path.basename(src.picture.name), src.picture)

        self.instance.position = (self.event.items.aggregate(p=Max('position'))['p'] or 0) + 1
        if not self.instance.admission:
            self.instance.personalized = False
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

        if self.cleaned_data.get('copy_from'):
            if not self.instance.all_sales_channels:
                self.instance.limit_sales_channels.set(self.cleaned_data['copy_from'].limit_sales_channels.all())
            self.instance.require_membership_types.set(
                self.cleaned_data['copy_from'].require_membership_types.all()
            )
        if self.cleaned_data.get('has_variations'):
            if self.cleaned_data.get('copy_from') and self.cleaned_data.get('copy_from').has_variations:
                for variation in self.cleaned_data['copy_from'].variations.all():
                    v = copy.copy(variation)
                    v.pk = None
                    v.item = instance
                    v.save()
                    if not variation.all_sales_channels:
                        v.limit_sales_channels.set(variation.limit_sales_channels.all())
                    for mv in variation.meta_values.all():
                        mv.pk = None
                        mv.variation = v
                        mv.save(force_insert=True)
            else:
                ItemVariation.objects.create(
                    item=instance, value=__('Standard')
                )

        if self.cleaned_data.get('copy_from'):
            for question in self.cleaned_data['copy_from'].questions.all():
                question.items.add(instance)
                question.log_action('pretix.event.question.changed', user=self.user, data={
                    'item_added': self.instance.pk
                })
            for a in self.cleaned_data['copy_from'].addons.all():
                instance.addons.create(addon_category=a.addon_category, min_count=a.min_count, max_count=a.max_count,
                                       price_included=a.price_included, position=a.position,
                                       multi_allowed=a.multi_allowed)
            for b in self.cleaned_data['copy_from'].bundles.all():
                instance.bundles.create(bundled_item=b.bundled_item, bundled_variation=b.bundled_variation,
                                        count=b.count, designated_price=b.designated_price)
            for pt in self.cleaned_data['copy_from'].program_times.all():
                instance.program_times.create(start=pt.start, end=pt.end)

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
            'personalized',
            'default_price',
            'tax_rule',
        ]


class ShowQuotaNullBooleanSelect(forms.NullBooleanSelect):
    def __init__(self, attrs=None):
        choices = (
            ('unknown', _('(Event default)')),
            ('true', _('Yes')),
            ('false', _('No')),
        )
        super(forms.NullBooleanSelect, self).__init__(attrs, choices)


class TicketNullBooleanSelect(forms.NullBooleanSelect):
    def __init__(self, attrs=None):
        choices = (
            ('unknown', _('Choose automatically depending on event settings')),
            ('true', _('Yes, if ticket generation is enabled in general')),
            ('false', _('Never')),
        )
        super(forms.NullBooleanSelect, self).__init__(attrs, choices)


class ItemUpdateForm(I18nModelForm):
    picture = ExtFileField(
        label=_('Product picture'),
        ext_whitelist=settings.FILE_UPLOAD_EXTENSIONS_IMAGE,
        max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tax_rule'].queryset = self.instance.event.tax_rules.all()
        self.fields['description'].widget.attrs['placeholder'] = _(
            'e.g. This reduced price is available for full-time students, jobless and people '
            'over 65. This ticket includes access to all parts of the event, except the VIP '
            'area.'
        )
        if self.event.tax_rules.exists():
            self.fields['tax_rule'].required = True
        self.fields['description'].widget.attrs['rows'] = '4'
        self.fields['limit_sales_channels'].queryset = self.event.organizer.sales_channels.all()
        self.fields['limit_sales_channels'].widget = SalesChannelCheckboxSelectMultiple(self.event, attrs={
            'data-inverse-dependency': '<[name$=all_sales_channels]',
        }, choices=self.fields['limit_sales_channels'].widget.choices)
        change_decimal_field(self.fields['default_price'], self.event.currency)

        self.fields['available_from_mode'].widget = ButtonGroupRadioSelect(
            choices=self.fields['available_from_mode'].choices,
            option_icons=Item.UNAVAIL_MODE_ICONS
        )

        self.fields['available_until_mode'].widget = ButtonGroupRadioSelect(
            choices=self.fields['available_until_mode'].choices,
            option_icons=Item.UNAVAIL_MODE_ICONS
        )

        self.fields['hide_without_voucher'].widget = ButtonGroupRadioSelect(
            choices=(
                (True, _("Hide product if unavailable")),
                (False, _("Show product with info on why it’s unavailable")),
            ),
            option_icons={
                True: 'eye-slash',
                False: 'info'
            },
            attrs={'data-checkbox-dependency': '#id_require_voucher'}
        )

        self.fields['hidden_if_item_available_mode'].widget = ButtonGroupRadioSelect(
            choices=self.fields['hidden_if_item_available_mode'].choices,
            option_icons=Item.UNAVAIL_MODE_ICONS
        )

        if self.instance.hidden_if_available_id:
            self.fields['hidden_if_available'].queryset = self.event.quotas.all()
            self.fields['hidden_if_available'].help_text = format_html(
                "<strong>{}</strong> {}",
                _("This option is deprecated. For new products, use the newer option below that refers to another "
                  "product instead of a quota."),
                self.fields['hidden_if_available'].help_text
            )
            self.fields['hidden_if_available'].widget = Select2(
                attrs={
                    'data-model-select2': 'generic',
                    'data-select2-url': reverse('control:event.items.quotas.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                    'data-placeholder': _('Shown independently of other products')
                }
            )
            self.fields['hidden_if_available'].widget.choices = self.fields['hidden_if_available'].choices
            self.fields['hidden_if_available'].required = False
        else:
            del self.fields['hidden_if_available']

        self.fields['hidden_if_item_available'].queryset = self.event.items.exclude(id=self.instance.id)
        self.fields['hidden_if_item_available'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.items.select2', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                }),
                'data-placeholder': _('Shown independently of other products')
            }
        )
        self.fields['hidden_if_item_available'].widget.choices = self.fields['hidden_if_item_available'].choices
        self.fields['hidden_if_item_available'].required = False

        self.fields['category'].queryset = self.instance.event.categories.all()
        self.fields['category'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.items.categories.select2', kwargs={
                    'event': self.instance.event.slug,
                    'organizer': self.instance.event.organizer.slug,
                }),
                'data-placeholder': _('No category'),
            }
        )
        self.fields['category'].widget.choices = self.fields['category'].choices

        self.fields['free_price_suggestion'].widget.attrs['data-display-dependency'] = '#id_free_price'

        self.fields['validity_dynamic_start_choice'] = forms.TypedChoiceField(
            label=_("Start of validity"),
            choices=(
                ("False", _("Purchase date")),
                ("True", _("Date chosen by customer")),
            ),
            coerce=lambda x: x == 'True',
        )

        qs = self.event.organizer.membership_types.all()
        if qs:
            self.fields['require_membership_types'].queryset = qs
            self.fields['grant_membership_type'].queryset = qs
            self.fields['grant_membership_type'].empty_label = _('No membership granted')
        else:
            del self.fields['require_membership']
            del self.fields['require_membership_types']
            del self.fields['grant_membership_type']
            del self.fields['grant_membership_duration_like_event']
            del self.fields['grant_membership_duration_days']
            del self.fields['grant_membership_duration_months']

        if not self.event.settings.reusable_media_active:
            del self.fields['media_type']
            del self.fields['media_policy']

    def clean(self):
        d = super().clean()
        if d['issue_giftcard']:
            if d['tax_rule'] and d['tax_rule'].rate > 0:
                self.add_error(
                    'tax_rule',
                    _("Gift card products should use a tax rule with a rate of 0 percent since sales tax will be applied when the gift card is redeemed.")
                )
            if d.get('validity_mode'):
                self.add_error(
                    'validity_mode',
                    _(
                        "Do not set a specific validity for gift card products as it will not restrict the validity "
                        "of the gift card. A validity of gift cards can be set in your organizer settings."
                    )
                )
            if d.get('admission'):
                self.add_error(
                    'admission',
                    _(
                        "Gift card products should not be admission products at the same time."
                    )
                )

        if not d.get('require_voucher'):
            d['hide_without_voucher'] = False

        if d.get('require_membership') and not d.get('require_membership_types'):
            self.add_error(
                'require_membership_types',
                _(
                    "If a valid membership is required, at least one valid membership type needs to be selected."
                )
            )

        if not d.get('admission'):
            d['personalized'] = False

        if d.get('grant_membership_type'):
            if not d['grant_membership_type'].transferable and not d['personalized']:
                self.add_error(
                    'personalized' if d.get('admission') else 'admission',
                    _("Your product grants a non-transferable membership and should therefore be a personalized "
                      "admission ticket. Otherwise customers might not be able to use the membership later. If you "
                      "want the membership to be non-personalized, set the membership type to be transferable.")
                )

        if d.get('validity_mode') == Item.VALIDITY_MODE_FIXED and d.get('validity_fixed_from') and d.get('validity_fixed_until'):
            if d.get('validity_fixed_from') > d.get('validity_fixed_until'):
                self.add_error(
                    'validity_fixed_from',
                    _("The start of validity must be before the end of validity.")
                )

        if d.get('validity_mode') == Item.VALIDITY_MODE_DYNAMIC:
            if not any(d.get(f'validity_dynamic_duration_{k}') for k in ('months', 'days', 'hours', 'minutes')):
                self.add_error(
                    'validity_dynamic_duration_months',
                    _("You have selected dynamic validity but have not entered a time period. This would render "
                      "the tickets unusable.")
                )

        Item.clean_media_settings(self.event, d.get('media_policy'), d.get('media_type'), d.get('issue_giftcard'))

        return d

    class Meta:
        model = Item
        localized_fields = '__all__'
        fields = [
            'category',
            'name',
            'internal_name',
            'active',
            'all_sales_channels',
            'limit_sales_channels',
            'admission',
            'personalized',
            'description',
            'picture',
            'default_price',
            'free_price',
            'free_price_suggestion',
            'tax_rule',
            'available_from',
            'available_from_mode',
            'available_until',
            'available_until_mode',
            'require_voucher',
            'require_approval',
            'hide_without_voucher',
            'allow_cancel',
            'allow_waitinglist',
            'max_per_order',
            'min_per_order',
            'checkin_attention',
            'checkin_text',
            'generate_tickets',
            'original_price',
            'require_bundling',
            'show_quota_left',
            'hidden_if_available',
            'hidden_if_item_available',
            'hidden_if_item_available_mode',
            'issue_giftcard',
            'require_membership',
            'require_membership_types',
            'require_membership_hidden',
            'grant_membership_type',
            'grant_membership_duration_like_event',
            'grant_membership_duration_days',
            'grant_membership_duration_months',
            'validity_mode',
            'validity_fixed_from',
            'validity_fixed_until',
            'validity_dynamic_duration_minutes',
            'validity_dynamic_duration_hours',
            'validity_dynamic_duration_days',
            'validity_dynamic_duration_months',
            'validity_dynamic_start_choice',
            'validity_dynamic_start_choice_day_limit',
            'media_policy',
            'media_type',
        ]
        field_classes = {
            'available_from': SplitDateTimeField,
            'available_until': SplitDateTimeField,
            'validity_fixed_from': SplitDateTimeField,
            'validity_fixed_until': SplitDateTimeField,
            'hidden_if_available': SafeModelChoiceField,
            'hidden_if_item_available': SafeModelChoiceField,
            'grant_membership_type': SafeModelChoiceField,
            'require_membership_types': SafeModelMultipleChoiceField,
            'limit_sales_channels': SafeModelMultipleChoiceField,
        }
        widgets = {
            'available_from': SplitDateTimePickerWidget(),
            'available_until': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_available_from_0'}),
            'validity_fixed_from': SplitDateTimePickerWidget(),
            'validity_fixed_until': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_validity_fixed_from_0'}),
            'require_membership_types': forms.CheckboxSelectMultiple(attrs={
                'class': 'scrolling-multiple-choice'
            }),
            'generate_tickets': TicketNullBooleanSelect(),
            'show_quota_left': ShowQuotaNullBooleanSelect(),
            'max_per_order': forms.widgets.NumberInput(attrs={'min': 0}),
            'min_per_order': forms.widgets.NumberInput(attrs={'min': 0}),
            'checkin_text': forms.TextInput(),
            'description': I18nMarkdownTextarea,
        }


class ItemVariationsFormSet(I18nFormSet):
    template = "pretixcontrol/item/include_variations.html"
    title = _('Variations')

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
        if should_delete and form.instance.pk and (form.instance.orderposition_set.exists() or form.instance.cartposition_set.exists()):
            form._delete_fail = True
            return False
        return form.cleaned_data.get(DELETION_FIELD_NAME, False)

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        kwargs['membership_types'] = self.mt
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        self.is_valid()
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            use_required_attribute=False,
            membership_types=self.mt,
            locales=self.locales,
            event=self.event
        )
        self.add_fields(form, None)
        return form

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mt = self.event.organizer.membership_types.all()


class ItemVariationForm(I18nModelForm):
    def __init__(self, *args, **kwargs):
        qs = kwargs.pop('membership_types')
        super().__init__(*args, **kwargs)
        change_decimal_field(self.fields['default_price'], self.event.currency)
        self.fields['limit_sales_channels'].queryset = self.event.organizer.sales_channels.all()
        self.fields['limit_sales_channels'].widget = SalesChannelCheckboxSelectMultiple(self.event, attrs={
            'data-inverse-dependency': '<[name$=all_sales_channels]',
        }, choices=self.fields['limit_sales_channels'].widget.choices)

        self.fields['description'].widget.attrs['rows'] = 3
        if qs:
            self.fields['require_membership_types'].queryset = qs
        else:
            del self.fields['require_membership']
            del self.fields['require_membership_types']

        self.fields['free_price_suggestion'].widget.attrs['data-display-dependency'] = '#id_free_price'

        self.fields['available_from_mode'].widget = ButtonGroupRadioSelect(
            choices=self.fields['available_from_mode'].choices,
            option_icons=Item.UNAVAIL_MODE_ICONS
        )

        self.fields['available_until_mode'].widget = ButtonGroupRadioSelect(
            choices=self.fields['available_until_mode'].choices,
            option_icons=Item.UNAVAIL_MODE_ICONS
        )

        self.meta_fields = []
        meta_defaults = {}
        if self.instance.pk:
            for mv in self.instance.meta_values.all():
                meta_defaults[mv.property_id] = mv.value
        for p in self.meta_properties:
            self.initial[f'meta_{p.name}'] = meta_defaults.get(p.pk)
            self.fields[f'meta_{p.name}'] = forms.CharField(
                label=p.name,
                widget=forms.TextInput(
                    attrs={
                        'placeholder': _('Use value from product'),
                        'data-typeahead-url': reverse('control:event.items.meta.typeahead', kwargs={
                            'organizer': self.event.organizer.slug,
                            'event': self.event.slug
                        }) + '?' + urlencode({
                            'property': p.name,
                        }),
                    },
                ),
                required=False,

            )
            self.meta_fields.append(f'meta_{p.name}')

    class Meta:
        model = ItemVariation
        localized_fields = '__all__'
        fields = [
            'value',
            'active',
            'default_price',
            'free_price_suggestion',
            'original_price',
            'description',
            'require_approval',
            'require_membership',
            'require_membership_hidden',
            'require_membership_types',
            'checkin_attention',
            'checkin_text',
            'available_from',
            'available_from_mode',
            'available_until',
            'available_until_mode',
            'all_sales_channels',
            'limit_sales_channels',
            'hide_without_voucher',
        ]
        field_classes = {
            'available_from': SplitDateTimeField,
            'available_until': SplitDateTimeField,
            'limit_sales_channels': SafeModelMultipleChoiceField,
        }
        widgets = {
            'available_from': SplitDateTimePickerWidget(),
            'available_until': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_available_from_0'}),
            'require_membership_types': forms.CheckboxSelectMultiple(attrs={
                'class': 'scrolling-multiple-choice'
            }),
            'checkin_text': forms.TextInput(),
        }

    def clean(self):
        d = super().clean()
        if d.get('require_membership') and not d.get('require_membership_types'):
            self.add_error(
                'require_membership_types',
                _(
                    "If a valid membership is required, at least one valid membership type needs to be selected."
                )
            )
        return d

    def save(self, commit=True):
        instance = super().save(commit)
        self.meta_fields = []
        current_values = {v.property_id: v for v in instance.meta_values.all()}
        for p in self.meta_properties:
            if self.cleaned_data[f'meta_{p.name}']:
                if p.pk in current_values:
                    current_values[p.pk].value = self.cleaned_data[f'meta_{p.name}']
                    current_values[p.pk].save()
                else:
                    instance.meta_values.create(property=p, value=self.cleaned_data[f'meta_{p.name}'])
            elif p.pk in current_values:
                current_values[p.pk].delete()

    @property
    def meta_properties(self):
        if not hasattr(self.event, '_cached_item_meta_properties'):
            self.event._cached_item_meta_properties = self.event.item_meta_properties.all()
        return self.event._cached_item_meta_properties


class ItemAddOnsFormSet(I18nFormSet):
    title = _('Add-ons')
    template = "pretixcontrol/item/include_addons.html"

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
        self.fields['addon_category'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.items.categories.select2', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                }),
            }
        )
        self.fields['addon_category'].widget.choices = self.fields['addon_category'].choices

    class Meta:
        model = ItemAddOn
        localized_fields = '__all__'
        fields = [
            'addon_category',
            'min_count',
            'max_count',
            'price_included',
            'multi_allowed',
        ]
        help_texts = {
            'min_count': _('Be aware that setting a minimal number makes it impossible to buy this product if all '
                           'available add-ons are sold out.')
        }


class ItemBundleFormSet(I18nFormSet):
    template = "pretixcontrol/item/include_bundles.html"
    title = _('Bundled products')

    def __init__(self, *args, **kwargs):
        self.event = kwargs.get('event')
        self.item = kwargs.pop('item')
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        kwargs['item'] = self.item
        kwargs['item_qs'] = self.item_qs
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
            item_qs=self.item_qs,
            item=self.item,
            event=self.event
        )
        self.add_fields(form, None)
        return form

    @cached_property
    def item_qs(self):
        return self.event.items.prefetch_related('variations').all()

    def clean(self):
        super().clean()
        ivs = set()
        for i in range(0, self.total_form_count()):
            form = self.forms[i]
            if self.can_delete:
                if self._should_delete_form(form):
                    # This form is going to be deleted so any of its errors
                    # should not cause the entire formset to be invalid.
                    try:
                        ivs.remove(form.cleaned_data['itemvar'])
                    except KeyError:
                        pass
                    continue

            if 'itemvar' in form.cleaned_data:
                if form.cleaned_data['itemvar'] in ivs:
                    raise ValidationError(_('You added the same bundled product twice.'))

                ivs.add(form.cleaned_data['itemvar'])


class ItemBundleForm(I18nModelForm):
    itemvar = forms.ChoiceField(label=_('Bundled product'))

    def __init__(self, *args, **kwargs):
        self.item = kwargs.pop('item')
        self.item_qs = kwargs.pop('item_qs')
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
        for i in self.item_qs:
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
        if not self.cleaned_data.get('designated_price'):
            d['designated_price'] = Decimal('0.00')
            self.instance.designated_price = Decimal('0.00')

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


class ItemMetaValueForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        self.property = kwargs.pop('property')
        super().__init__(*args, **kwargs)
        if self.property.allowed_values:
            self.fields['value'] = forms.ChoiceField(
                label=self.property.name,
                choices=[(
                    "", _("Default ({value})").format(value=self.property.default)
                    if self.property.default else ""
                )] + [(a.strip(), a.strip()) for a in self.property.allowed_values.splitlines()]
            )
        else:
            self.fields['value'].label = self.property.name
            self.fields['value'].widget.attrs['placeholder'] = self.property.default
            self.fields['value'].widget.attrs['data-typeahead-url'] = (
                reverse('control:event.items.meta.typeahead', kwargs={
                    'organizer': self.property.event.organizer.slug,
                    'event': self.property.event.slug
                }) + '?' + urlencode({
                    'property': self.property.name,
                })
            )
        self.fields['value'].required = self.property.required and not self.property.default

    class Meta:
        model = ItemMetaValue
        fields = ['value']
        widgets = {
            'value': forms.TextInput()
        }


class ItemProgramTimeFormSet(I18nFormSet):
    template = "pretixcontrol/item/include_program_times.html"
    title = _('Program times')

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


class ItemProgramTimeForm(I18nModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['end'].widget.attrs['data-date-after'] = '#id_{prefix}-start_0'.format(prefix=self.prefix)

    class Meta:
        model = ItemProgramTime
        localized_fields = '__all__'
        fields = [
            'start',
            'end',
        ]
        field_classes = {
            'start': forms.SplitDateTimeField,
            'end': forms.SplitDateTimeField,
        }
        widgets = {
            'start': SplitDateTimePickerWidget(),
            'end': SplitDateTimePickerWidget(),
        }
