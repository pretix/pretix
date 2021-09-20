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
from django import forms
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils.translation import gettext_lazy as _
from phonenumber_field.formfields import PhoneNumberField
from phonenumbers.data import _COUNTRY_CODE_TO_REGION_CODE

from pretix.base.forms.questions import (
    NamePartsFormField, WrappedPhoneNumberPrefixWidget, guess_country,
)
from pretix.base.i18n import get_babel_locale, language
from pretix.base.models import Quota, WaitingListEntry
from pretix.presale.views.event import get_grouped_items


class WaitingListForm(forms.ModelForm):
    required_css_class = 'required'

    class Meta:
        model = WaitingListEntry
        fields = ('name_parts', 'email', 'phone')

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        self.channel = kwargs.pop('channel')
        super().__init__(*args, **kwargs)

        choices = [
            ('', '')
        ]
        items, display_add_to_cart = get_grouped_items(
            self.event, self.instance.subevent, require_seat=None
        )
        for i in items:
            if not i.allow_waitinglist:
                continue

            if i.has_variations:
                for v in i.available_variations:
                    if v.cached_availability[0] == Quota.AVAILABILITY_OK:
                        continue
                    choices.append((f'{i.pk}-{v.pk}', f'{i.name} – {v.value}'))

            else:
                if i.cached_availability[0] == Quota.AVAILABILITY_OK:
                    continue
                choices.append((f'{i.pk}', f'{i.name}'))

        self.fields['itemvar'] = forms.ChoiceField(
            label=_('Product'),
            choices=choices,
        )

        event = self.event

        if event.settings.waiting_list_names_asked:
            self.fields['name_parts'] = NamePartsFormField(
                max_length=255,
                required=event.settings.waiting_list_names_required,
                scheme=event.settings.name_scheme,
                titles=event.settings.name_scheme_titles,
                label=_('Name'),
            )
        else:
            del self.fields['name_parts']

        if event.settings.waiting_list_phones_asked:
            with language(get_babel_locale()):
                default_country = guess_country(self.event)
                for prefix, values in _COUNTRY_CODE_TO_REGION_CODE.items():
                    if str(default_country) in values and not self.initial.get('phone'):
                        # We now exploit an implementation detail in PhoneNumberPrefixWidget to allow us to pass just
                        # a country code but no number as an initial value. It's a bit hacky, but should be stable for
                        # the future.
                        self.initial['phone'] = "+{}.".format(prefix)

                self.fields['phone'] = PhoneNumberField(
                    label=_("Phone number"),
                    required=event.settings.waiting_list_phones_required,
                    help_text=event.settings.waiting_list_phones_explanation_text,
                    widget=WrappedPhoneNumberPrefixWidget()
                )
        else:
            del self.fields['phone']

    def clean(self):
        try:
            iv = self.data.get('itemvar', '')
            if '-' in iv:
                itemid, varid = iv.split('-')
            else:
                itemid, varid = iv, None

            self.instance.item = self.instance.event.items.get(pk=itemid)
            if varid:
                self.instance.variation = self.instance.item.variations.get(pk=varid)
            else:
                self.instance.variation = None

        except ObjectDoesNotExist:
            raise ValidationError(_("Invalid product selected."))

        data = super().clean()
        return data
