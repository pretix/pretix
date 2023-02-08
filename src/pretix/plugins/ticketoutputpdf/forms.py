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
from django.utils.translation import gettext_lazy as _

from pretix.base.services import tickets

from .models import TicketLayout, TicketLayoutItem


class TicketLayoutForm(forms.ModelForm):
    class Meta:
        model = TicketLayout
        fields = ('name',)


class TicketLayoutItemForm(forms.ModelForm):
    is_layouts = True

    class Meta:
        model = TicketLayoutItem
        fields = ('layout',)

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        self.sales_channel = kwargs.pop('sales_channel')
        queryset = kwargs.pop('queryset')
        super().__init__(*args, **kwargs)
        if self.sales_channel.identifier != 'web':
            self.fields['layout'].label = _('PDF ticket layout for {channel}').format(
                channel=self.sales_channel.verbose_name
            )
            self.fields['layout'].empty_label = _('(Same as above)')
        else:
            self.fields['layout'].label = _('PDF ticket layout')
            self.fields['layout'].empty_label = _('(Event default)')
        self.fields['layout'].queryset = queryset
        self.fields['layout'].required = False

    def save(self, commit=True):
        self.instance.sales_channel = self.sales_channel.identifier
        if self.cleaned_data['layout'] is None:
            if self.instance.pk:
                self.instance.delete()
            else:
                return
        else:
            return super().save(commit=commit)
        tickets.invalidate_cache.apply_async(kwargs={'event': self.event.pk, 'provider': 'pdf',
                                                     'item': self.instance.item_id})
