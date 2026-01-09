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
from django.forms import ChoiceField, EmailField
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField
from phonenumber_field.formfields import PhoneNumberField

from pretix.base.forms import I18nModelForm
from pretix.base.forms.questions import NamePartsFormField
from pretix.base.models import Item, ItemVariation, WaitingListEntry
from pretix.control.forms.widgets import Select2, Select2ItemVarQuota


class WaitingListEntryEditForm(I18nModelForm):
    itemvar = ChoiceField()

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.get('instance', None)
        initial = kwargs.get('initial', {})

        choices = []
        if self.instance and self.instance.pk and 'itemvar' not in initial:
            if self.instance.variation is not None:
                initial['itemvar'] = f'{self.instance.item.pk}-{self.instance.variation.pk}'
                if self.instance.variation.active is False:
                    choices.append((initial['itemvar'], str(self.instance.variation)))
            else:
                initial['itemvar'] = self.instance.item.pk
                if self.instance.item.active is False:
                    choices.append((initial['itemvar'], str(self.instance)))

        kwargs['initial'] = initial

        super().__init__(*args, **kwargs)

        if self.event.has_subevents:
            self.fields['subevent'].required = True
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
        else:
            del self.fields['subevent']

        if self.event.settings.waiting_list_names_asked:
            self.fields['name_parts'] = NamePartsFormField(
                max_length=255,
                required=self.event.settings.waiting_list_names_required,
                scheme=self.event.organizer.settings.name_scheme,
                titles=self.event.organizer.settings.name_scheme_titles,
                label=_('Name'),
            )
        else:
            del self.fields['name_parts']

        if not self.event.settings.waiting_list_phones_asked:
            del self.fields['phone']


        items = self.event.items.filter(active=True).prefetch_related('variations')

        for item in items:
            active_variations = item.variations.filter(active=True)
            if len(active_variations) > 0:
                for variation in active_variations:
                    choices.append(
                        ('{}-{}'.format(item.pk, variation.pk), str(variation))
                    )
            else:
                choices.append(('{}'.format(item.pk), str(item)))

        self.fields['itemvar'].label = _("Product")
        self.fields['itemvar'].help_text = _("Only includes active products.")
        self.fields['itemvar'].required = True
        self.fields['itemvar'].choices = choices

    def clean(self):
        cleaned_data = super().clean()

        if self.instance.voucher is not None:
            raise ValidationError(_('A voucher for this waiting list entry was sent out already.'))

        itemvar = cleaned_data.get('itemvar')

        if itemvar:
            self.instance.item = self.event.items.get(pk=itemvar.split('-')[0])
            if '-' in itemvar:
                self.instance.variation = self.instance.item.variations.get(pk=itemvar.split('-')[1])

        if ((self.instance.item and not self.instance.item.active) or
                (self.instance.variation and not self.instance.variation.active)):
            self.add_error('itemvar', _('The selected product is not active.'))

        return cleaned_data

    class Meta:
        model = WaitingListEntry
        fields = [
            'email',
            'name_parts',
            'phone',
            'subevent',
        ]
        field_classes = {
            'subevent': SafeModelChoiceField,
            'email': EmailField,
            'phone': PhoneNumberField,
        }
        exclude = [
            'voucher',  # handled by the assign operation in the WaitingListActionView
            'priority'  # handled via thumbs up/down
        ]
