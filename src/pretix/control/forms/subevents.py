#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
from datetime import datetime
from urllib.parse import urlencode

from django import forms
from django.core.exceptions import ValidationError
from django.forms import formset_factory
from django.forms.utils import ErrorDict
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from i18nfield.forms import I18nInlineFormSet

from pretix.base.forms import I18nModelForm
from pretix.base.forms.widgets import DatePickerWidget, TimePickerWidget
from pretix.base.models.event import SubEvent, SubEventMetaValue
from pretix.base.models.items import SubEventItem, SubEventItemVariation
from pretix.base.reldate import RelativeDateTimeField, RelativeDateWrapper
from pretix.base.templatetags.money import money_filter
from pretix.control.forms import SplitDateTimeField, SplitDateTimePickerWidget
from pretix.control.forms.rrule import RRuleForm
from pretix.helpers.money import change_decimal_field


class SubEventForm(I18nModelForm):
    def __init__(self, *args, **kwargs):
        self.event = kwargs['event']
        instance = kwargs.get('instance')
        if instance and not instance.name:
            kwargs['initial'].setdefault('name', self.event.name)
            kwargs['initial'].setdefault('location', self.event.location)
            kwargs['initial'].setdefault('geo_lat', self.event.geo_lat)
            kwargs['initial'].setdefault('geo_lon', self.event.geo_lon)
        super().__init__(*args, **kwargs)
        self.fields['location'].widget.attrs['rows'] = '3'

    class Meta:
        model = SubEvent
        localized_fields = '__all__'
        fields = [
            'name',
            'active',
            'is_public',
            'date_from',
            'date_to',
            'date_admission',
            'presale_start',
            'presale_end',
            'location',
            'frontpage_text',
            'geo_lat',
            'geo_lon',
        ]
        field_classes = {
            'date_from': SplitDateTimeField,
            'date_to': SplitDateTimeField,
            'date_admission': SplitDateTimeField,
            'presale_start': SplitDateTimeField,
            'presale_end': SplitDateTimeField,
        }
        widgets = {
            'date_from': SplitDateTimePickerWidget(),
            'date_to': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_date_from_0'}),
            'date_admission': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_date_from_0'}),
            'presale_start': SplitDateTimePickerWidget(),
            'presale_end': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_presale_start_0'}),
        }


class SubEventBulkForm(SubEventForm):
    rel_presale_start = RelativeDateTimeField(
        label=_('Start of presale'),
        help_text=_('Optional. No products will be sold before this date.'),
        required=False,
        limit_choices=('date_from', 'date_to'),
    )
    rel_presale_end = RelativeDateTimeField(
        label=_('End of presale'),
        help_text=_('Optional. No products will be sold after this date. If you do not set this value, the presale '
                    'will end after the end date of your event.'),
        required=False,
        limit_choices=('date_from', 'date_to'),
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs['event']
        super().__init__(*args, **kwargs)
        self.fields['location'].widget.attrs['rows'] = '3'
        del self.fields['date_from']
        del self.fields['date_to']
        del self.fields['date_admission']


class NullBooleanSelect(forms.NullBooleanSelect):
    def __init__(self, attrs=None):
        choices = (
            ('unknown', _('Keep the current values')),
            ('true', _('Yes')),
            ('false', _('No')),
        )
        super(forms.NullBooleanSelect, self).__init__(attrs, choices)


class SubEventBulkEditForm(I18nModelForm):
    def __init__(self, *args, **kwargs):
        self.mixed_values = kwargs.pop('mixed_values')
        self.queryset = kwargs.pop('queryset')
        super().__init__(*args, **kwargs)
        self.fields['location'].widget.attrs['rows'] = '3'

        for k in ('name', 'location', 'frontpage_text'):
            # i18n fields
            if k in self.mixed_values:
                self.fields[k].widget.attrs['placeholder'] = '[{}]'.format(_('Selection contains various values'))
            else:
                self.fields[k].widget.attrs['placeholder'] = ''
            self.fields[k].one_required = False

        for k in ('geo_lat', 'geo_lon'):
            # scalar fields
            if k in self.mixed_values:
                self.fields[k].widget.attrs['placeholder'] = '[{}]'.format(_('Selection contains various values'))
            else:
                self.fields[k].widget.attrs['placeholder'] = ''
            self.fields[k].widget.is_required = False
            self.fields[k].required = False

        for k in ('date_from', 'date_to', 'date_admission', 'presale_start', 'presale_end'):
            self.fields[k + '_day'] = forms.DateField(
                label=self._meta.model._meta.get_field(k).verbose_name,
                help_text=self._meta.model._meta.get_field(k).help_text,
                widget=DatePickerWidget(),
                required=False,
            )
            self.fields[k + '_time'] = forms.TimeField(
                label=self._meta.model._meta.get_field(k).verbose_name,
                help_text=self._meta.model._meta.get_field(k).help_text,
                widget=TimePickerWidget(),
                required=False,
            )

    class Meta:
        model = SubEvent
        localized_fields = '__all__'
        fields = [
            'name',
            'location',
            'frontpage_text',
            'geo_lat',
            'geo_lon',
            'is_public',
            'active',
        ]
        field_classes = {
        }
        widgets = {
        }

    def save(self, commit=True):
        objs = list(self.queryset)
        fields = set()

        check_map = {
            'geo_lat': '__geo',
            'geo_lon': '__geo',
        }
        for k in self.fields:
            cb_val = self.prefix + check_map.get(k, k)
            if cb_val not in self.data.getlist('_bulk'):
                continue

            if k.endswith('_day'):
                for obj in objs:
                    oldval = getattr(obj, k.replace('_day', ''))
                    cval = self.cleaned_data[k]
                    if cval is None:
                        newval = None
                        if not self._meta.model._meta.get_field(k.replace('_day', '')).null:
                            continue
                    elif oldval:
                        oldval = oldval.astimezone(self.event.timezone)
                        newval = oldval.replace(
                            year=cval.year,
                            month=cval.month,
                            day=cval.day,
                        )
                    else:
                        # If there is no previous date/time set, we'll just set to midnight
                        # If the user also selected a time, this will be overridden anyways
                        newval = datetime(
                            year=cval.year,
                            month=cval.month,
                            day=cval.day,
                            tzinfo=self.event.timezone
                        )
                    setattr(obj, k.replace('_day', ''), newval)
                fields.add(k.replace('_day', ''))
            elif k.endswith('_time'):
                for obj in objs:
                    # If there is no previous date/time set and only a time is changed not the
                    # date, we instead use the date of the event
                    oldval = getattr(obj, k.replace('_time', '')) or obj.date_from
                    cval = self.cleaned_data[k]
                    if cval is None:
                        continue
                    oldval = oldval.astimezone(self.event.timezone)
                    newval = oldval.replace(
                        hour=cval.hour,
                        minute=cval.minute,
                        second=cval.second,
                    )
                    setattr(obj, k.replace('_time', ''), newval)
                fields.add(k.replace('_time', ''))
            else:
                fields.add(k)
                for obj in objs:
                    setattr(obj, k, self.cleaned_data[k])

        if fields:
            SubEvent.objects.bulk_update(objs, fields, 200)

    def full_clean(self):
        if len(self.data) == 0:
            # form wasn't submitted
            self._errors = ErrorDict()
            return
        super().full_clean()


class SubEventItemOrVariationFormMixin:
    def __init__(self, *args, **kwargs):
        self.item = kwargs.pop('item')
        self.variation = kwargs.pop('variation', None)
        super().__init__(*args, **kwargs)
        change_decimal_field(self.fields['price'], self.item.event.currency)


class SubEventItemForm(SubEventItemOrVariationFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].widget.attrs['placeholder'] = money_filter(self.item.default_price, self.item.event.currency, hide_currency=True)
        self.fields['price'].label = str(self.item)

    class Meta:
        model = SubEventItem
        fields = ['price', 'disabled', 'available_from', 'available_until']
        widgets = {
            'available_from': SplitDateTimePickerWidget(),
            'available_until': SplitDateTimePickerWidget(),
            'price': forms.TextInput
        }
        field_classes = {
            'available_from': SplitDateTimeField,
            'available_until': SplitDateTimeField,
        }

    def clean(self):
        d = super().clean()
        if d.get('available_from') and d.get('available_until'):
            if d.get('available_from') > d.get('available_until'):
                raise ValidationError(_('The end of availability should be after the start of availability.'))
        return d


class SubEventItemVariationForm(SubEventItemOrVariationFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].widget.attrs['placeholder'] = money_filter(self.variation.price, self.item.event.currency, hide_currency=True)
        self.fields['price'].label = '{} – {}'.format(str(self.item), self.variation.value)

    class Meta:
        model = SubEventItemVariation
        fields = ['price', 'disabled', 'available_from', 'available_until']
        widgets = {
            'available_from': SplitDateTimePickerWidget(),
            'available_until': SplitDateTimePickerWidget(),
            'price': forms.TextInput
        }
        field_classes = {
            'available_from': SplitDateTimeField,
            'available_until': SplitDateTimeField,
        }

    def clean(self):
        d = super().clean()
        if d.get('available_from') and d.get('available_until'):
            if d.get('available_from') > d.get('available_until'):
                raise ValidationError(_('The end of availability should be after the start of availability.'))
        return d


class BulkSubEventItemForm(SubEventItemForm):
    rel_available_from = RelativeDateTimeField(
        label=_('Available from'),
        required=False,
        limit_choices=('date_from', 'date_to'),
    )
    rel_available_until = RelativeDateTimeField(
        label=_('Available until'),
        required=False,
        limit_choices=('date_from', 'date_to'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields['available_from']
        del self.fields['available_until']
        if self.instance and self.instance.available_from and 'rel_available_from' not in self.initial:
            self.initial['rel_available_from'] = RelativeDateWrapper(self.instance.available_from)
        if self.instance and self.instance.available_until and 'rel_available_until' not in self.initial:
            self.initial['rel_available_until'] = RelativeDateWrapper(self.instance.available_until)


class BulkSubEventItemVariationForm(SubEventItemVariationForm):
    rel_available_from = RelativeDateTimeField(
        label=_('Available from'),
        required=False,
        limit_choices=('date_from', 'date_to'),
    )
    rel_available_until = RelativeDateTimeField(
        label=_('Available_until'),
        required=False,
        limit_choices=('date_from', 'date_to'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields['available_from']
        del self.fields['available_until']
        if self.instance and self.instance.available_from and 'rel_available_from' not in self.initial:
            self.initial['rel_available_from'] = RelativeDateWrapper(self.instance.available_from)
        if self.instance and self.instance.available_until and 'rel_available_until' not in self.initial:
            self.initial['rel_available_until'] = RelativeDateWrapper(self.instance.available_until)


class QuotaFormSet(I18nInlineFormSet):

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        self.locales = self.event.settings.get('locales')
        super().__init__(*args, **kwargs)

    @cached_property
    def items(self):
        return self.event.items.prefetch_related('variations').all()

    def _construct_form(self, i, **kwargs):
        kwargs['locales'] = self.locales
        kwargs['event'] = self.event
        kwargs['items'] = self.items
        kwargs['items'] = self.items
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            use_required_attribute=False,
            locales=self.locales,
            event=self.event,
            items=self.items
        )
        self.add_fields(form, None)
        return form


class SubEventMetaValueForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        self.property = kwargs.pop('property')
        self.default = kwargs.pop('default', None)
        self.disabled = kwargs.pop('disabled', False)
        super().__init__(*args, **kwargs)
        if self.property.allowed_values:
            self.fields['value'] = forms.ChoiceField(
                label=self.property.name,
                choices=[
                    ('', _('Default ({value})').format(value=self.default or self.property.default) if self.default or self.property.default else ''),
                ] + [(a.strip(), a.strip()) for a in self.property.allowed_values.splitlines()],
            )
        else:
            self.fields['value'].label = self.property.name
            self.fields['value'].widget.attrs['placeholder'] = self.default or self.property.default
            self.fields['value'].widget.attrs['data-typeahead-url'] = (
                reverse('control:events.meta.typeahead') + '?' + urlencode({
                    'property': self.property.name,
                    'organizer': self.property.organizer.slug,
                })
            )
        self.fields['value'].required = False
        if self.disabled:
            self.fields['value'].widget.attrs['readonly'] = 'readonly'

    def clean_slug(self):
        if self.disabled:
            return self.instance.value if self.instance else None
        return self.cleaned_data['slug']

    class Meta:
        model = SubEventMetaValue
        fields = ['value']
        widgets = {
            'value': forms.TextInput
        }


class CheckinListFormSet(I18nInlineFormSet):

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        self.locales = self.event.settings.get('locales')
        super().__init__(*args, **kwargs)

    @cached_property
    def items(self):
        return self.event.items.prefetch_related('variations').all()

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            use_required_attribute=False,
            event=self.event,
        )
        self.add_fields(form, None)
        return form


class RRuleFormSetForm(RRuleForm):
    exclude = forms.BooleanField(
        label=_('Exclude these dates instead of adding them.'),
        required=False
    )


RRuleFormSet = formset_factory(
    RRuleFormSetForm,
    can_order=False, can_delete=True, extra=1
)


class TimeForm(forms.Form):
    time_from = forms.TimeField(
        label=_('Event start time'),
        widget=forms.TimeInput(attrs={'class': 'timepickerfield', 'autocomplete': 'off'}),
        required=True
    )
    time_to = forms.TimeField(
        label=_('Event end time'),
        widget=forms.TimeInput(attrs={'class': 'timepickerfield', 'autocomplete': 'off'}),
        required=False
    )
    time_admission = forms.TimeField(
        label=_('Admission time'),
        widget=forms.TimeInput(attrs={'class': 'timepickerfield', 'autocomplete': 'off'}),
        required=False
    )


TimeFormSet = formset_factory(
    TimeForm,
    min_num=1,
    can_order=False, can_delete=True, extra=1, validate_min=True
)
