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

from pretix.base.services.orderimport import get_all_columns


class ProcessForm(forms.Form):
    orders = forms.ChoiceField(
        label=_('Import mode'),
        choices=(
            ('many', _('Create a separate order for each line')),
            ('one', _('Create one order with one position per line')),
        )
    )
    status = forms.ChoiceField(
        label=_('Order status'),
        choices=(
            ('paid', _('Create orders as fully paid')),
            ('pending', _('Create orders as pending and still require payment')),
        )
    )
    testmode = forms.BooleanField(
        label=_('Create orders as test mode orders'),
        required=False
    )

    def __init__(self, *args, **kwargs):
        headers = kwargs.pop('headers')
        initital = kwargs.pop('initial', {})
        self.event = kwargs.pop('event')
        initital['testmode'] = self.event.testmode
        kwargs['initial'] = initital
        super().__init__(*args, **kwargs)

        header_choices = [
            ('csv:{}'.format(h), _('CSV column: "{name}"').format(name=h)) for h in headers
        ]

        for c in get_all_columns(self.event):
            choices = []
            if c.default_value:
                choices.append((c.default_value, c.default_label))
            choices += header_choices
            for k, v in c.static_choices():
                choices.append(('static:{}'.format(k), v))

            self.fields[c.identifier] = forms.ChoiceField(
                label=str(c.verbose_name),
                choices=choices,
                widget=forms.Select(
                    attrs={'data-static': 'true'}
                )
            )
