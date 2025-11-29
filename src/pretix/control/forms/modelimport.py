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
from django import forms
from django.core.exceptions import ValidationError
from django.utils.functional import lazy
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from pretix.base.modelimport_orders import get_order_import_columns
from pretix.base.modelimport_vouchers import get_voucher_import_columns


class ProcessForm(forms.Form):

    def __init__(self, *args, **kwargs):
        headers = kwargs.pop('headers')
        initital = kwargs.pop('initial', {}) or {}
        kwargs['initial'] = initital
        columns = self.get_columns()
        column_keys = {c.identifier for c in columns}

        if not initital or all(k not in column_keys for k in initital.keys()):
            for c in columns:
                initital.setdefault(c.identifier, c.initial)
                for h in headers:
                    if h == c.identifier or h == str(c.verbose_name):
                        initital[c.identifier] = 'csv:{}'.format(h)
                        break

        super().__init__(*args, **kwargs)

        header_choices = [
            ('csv:{}'.format(h), _('CSV column: "{name}"').format(name=h)) for h in headers
        ]

        for c in columns:
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
                ),
                help_text=c.help_text,
            )

    def get_columns(self):
        raise NotImplementedError()  # noqa


format_html_lazy = lazy(format_html, str)


class OrdersProcessForm(ProcessForm):
    orders = forms.ChoiceField(
        label=_('Import mode'),
        choices=(
            ('many', _('Create a separate order for each line')),
            ('one', _('Create one order with one position per line')),
            ('mixed', _('Group multiple lines together into the same order based on a grouping column')),
        ),
        widget=forms.RadioSelect,
    )
    status = forms.ChoiceField(
        label=_('Order status'),
        choices=(
            ('paid', _('Create orders as fully paid')),
            ('pending', _('Create orders as pending and still require payment')),
        ),
        widget=forms.RadioSelect,
    )
    testmode = forms.BooleanField(
        label=_('Create orders as test mode orders'),
        required=False,
        help_text=format_html_lazy(
            '<div class="alert alert-warning" data-display-dependency="#id_testmode" data-inverse>{}</div>',
            _('Orders not created in test mode cannot be deleted again after import.')
        )
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        initital = kwargs.pop('initial', {})
        initital['testmode'] = self.event.testmode
        kwargs['initial'] = initital
        super().__init__(*args, **kwargs)
        if not self.event.testmode:
            self.fields["testmode"].help_text = ""

    def get_columns(self):
        return get_order_import_columns(self.event)

    def clean(self):
        data = super().clean()

        grouping = data.get("grouping") and data.get("grouping") != "empty"
        if data.get("orders") != "mixed" and grouping:
            raise ValidationError({"grouping": [_("A grouping cannot be specified for this import mode.")]})
        if data.get("orders") == "mixed" and not grouping:
            raise ValidationError({"grouping": [_("A grouping needs to be specified for this import mode.")]})

        return data


class VouchersProcessForm(ProcessForm):

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

    def get_columns(self):
        return get_voucher_import_columns(self.event)
