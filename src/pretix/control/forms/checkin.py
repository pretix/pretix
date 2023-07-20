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
from datetime import datetime, timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.timezone import get_current_timezone, make_aware, now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes.forms import (
    SafeModelChoiceField, SafeModelMultipleChoiceField,
)

from pretix.base.channels import get_all_sales_channels
from pretix.base.forms.widgets import SplitDateTimePickerWidget
from pretix.base.models.checkin import Checkin, CheckinList
from pretix.control.forms import ItemMultipleChoiceField
from pretix.control.forms.widgets import Select2


class NextTimeField(forms.TimeField):
    def to_python(self, value):
        value = super().to_python(value)
        if value is None:
            return
        tz = get_current_timezone()
        result = make_aware(datetime.combine(
            now().astimezone(tz).date(),
            value,
        ), tz)
        if result <= now():
            result += timedelta(days=1)
        return result


class NextTimeInput(forms.TimeInput):
    def format_value(self, value):
        if isinstance(value, datetime):
            value = value.astimezone(get_current_timezone()).time()
        return super().format_value(value)


class CheckinListForm(forms.ModelForm):
    def __init__(self, **kwargs):
        self.event = kwargs.pop('event')
        kwargs.pop('locales', None)
        super().__init__(**kwargs)
        self.fields['limit_products'].queryset = self.event.items.all()
        self.fields['auto_checkin_sales_channels'] = forms.MultipleChoiceField(
            label=self.fields['auto_checkin_sales_channels'].label,
            help_text=self.fields['auto_checkin_sales_channels'].help_text,
            required=self.fields['auto_checkin_sales_channels'].required,
            choices=(
                (c.identifier, c.verbose_name) for c in get_all_sales_channels().values()
            ),
            widget=forms.CheckboxSelectMultiple
        )

        if not self.event.organizer.gates.exists():
            del self.fields['gates']
        else:
            self.fields['gates'].queryset = self.event.organizer.gates.all()

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'All dates')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
        else:
            del self.fields['subevent']

    class Meta:
        model = CheckinList
        localized_fields = '__all__'
        fields = [
            'name',
            'all_products',
            'limit_products',
            'subevent',
            'include_pending',
            'auto_checkin_sales_channels',
            'allow_multiple_entries',
            'allow_entry_after_exit',
            'rules',
            'gates',
            'exit_all_at',
            'addon_match',
        ]
        widgets = {
            'limit_products': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '<[name$=all_products]'
            }),
            'gates': forms.CheckboxSelectMultiple(attrs={
                'class': 'scrolling-multiple-choice'
            }),
            'auto_checkin_sales_channels': forms.CheckboxSelectMultiple(),
            'exit_all_at': NextTimeInput(attrs={'class': 'timepickerfield'}),
        }
        field_classes = {
            'limit_products': ItemMultipleChoiceField,
            'gates': SafeModelMultipleChoiceField,
            'subevent': SafeModelChoiceField,
            'exit_all_at': NextTimeField,
        }

    def clean(self):
        d = super().clean()
        d['rules'] = CheckinList.validate_rules(d.get('rules'))

        if d.get('addon_match') and d.get('all_products'):
            raise ValidationError(_('If you allow checking in add-on tickets by scanning the main ticket, you must '
                                    'select a specific set of products for this check-in list, only including the '
                                    'possible add-on products.'))

        return d


class SimpleCheckinListForm(forms.ModelForm):
    def __init__(self, **kwargs):
        self.event = kwargs.pop('event')
        kwargs.pop('locales', None)
        super().__init__(**kwargs)
        self.fields['limit_products'].queryset = self.event.items.all()

        if not self.event.organizer.gates.exists():
            del self.fields['gates']
        else:
            self.fields['gates'].queryset = self.event.organizer.gates.all()

    class Meta:
        model = CheckinList
        localized_fields = '__all__'
        fields = [
            'name',
            'all_products',
            'limit_products',
            'include_pending',
            'allow_entry_after_exit',
            'gates',
        ]
        widgets = {
            'limit_products': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '<[name$=all_products]'
            }),
            'gates': forms.CheckboxSelectMultiple(attrs={
                'class': 'scrolling-multiple-choice'
            }),
        }
        field_classes = {
            'limit_products': ItemMultipleChoiceField,
            'subevent': SafeModelChoiceField,
            'gates': SafeModelMultipleChoiceField,
        }


class CheckinListSimulatorForm(forms.Form):
    raw_barcode = forms.CharField(
        label=_("Barcode"),
    )
    datetime = forms.SplitDateTimeField(
        label=_("Check-in time"),
        widget=SplitDateTimePickerWidget(),
    )
    checkin_type = forms.ChoiceField(
        label=_("Check-in type"),
        choices=Checkin.CHECKIN_TYPES,
    )
    ignore_unpaid = forms.BooleanField(
        label=_("Allow check-in of unpaid order (if check-in list permits it)"),
        required=False,
    )
    questions_supported = forms.BooleanField(
        label=_("Support for check-in questions"),
        initial=True,
        required=False,
    )
