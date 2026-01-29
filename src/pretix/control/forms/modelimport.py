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
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from pretix.base.email import get_available_placeholders
from pretix.base.forms import PlaceholderValidator
from pretix.base.forms.widgets import format_placeholders_help_text
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
                )
            )

    def get_columns(self):
        raise NotImplementedError()  # noqa


class OrdersProcessForm(ProcessForm):
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
        self.event = kwargs.pop('event')
        initital = kwargs.pop('initial', {})
        initital['testmode'] = self.event.testmode
        kwargs['initial'] = initital
        super().__init__(*args, **kwargs)

    def get_columns(self):
        return get_order_import_columns(self.event)


class VouchersProcessForm(ProcessForm):

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        initital = kwargs.get('initial', {}) or {}
        super().__init__(*args, **kwargs)
        self.fields['send'] = forms.BooleanField(
            label=_("Send vouchers via email"),
            required=False,
            initial=initital.get('send', False)
        )
        self.fields['send_subject'] = forms.CharField(
            label=_("Subject"),
            required=False,
            initial=initital.get('send_subject', _('Your voucher for {event}')),
            widget=forms.TextInput(attrs={'data-display-dependency': '#id_send'}),
        )
        self.fields['send_message'] = forms.CharField(
            label=_("Message"),
            required=False,
            initial=initital.get('send_message', _('Hello,\n\n'
                                                  'with this email, we\'re sending you a voucher for {event}:\n\n'
                                                  '{voucher_list}\n\n'
                                                  'You can redeem it here in our ticket shop:\n\n{url}\n\n'
                                                  'Best regards,  \n'
                                                  'Your {event} team')),
            widget=forms.Textarea(attrs={'data-display-dependency': '#id_send'}),
        )
        self._set_field_placeholders('send_subject', ['event', 'name'])
        self._set_field_placeholders('send_message', ['event', 'voucher_list', 'name'])
        if 'email' in self.fields:
            self.fields['email'].widget.attrs['data-display-dependency'] = '#id_send'
        if 'name' in self.fields:
            self.fields['name'].widget.attrs['data-display-dependency'] = '#id_send'

    def _set_field_placeholders(self, fn, base_parameters):
        placeholders = get_available_placeholders(self.event, base_parameters)
        ht = format_placeholders_help_text(placeholders, self.event)

        if self.fields[fn].help_text:
            self.fields[fn].help_text += ' ' + str(ht)
        else:
            self.fields[fn].help_text = ht
        self.fields[fn].validators.append(
            PlaceholderValidator(['{%s}' % p for p in placeholders.keys()])
        )

    def get_columns(self):
        return get_voucher_import_columns(self.event)

    def clean(self):
        data = super().clean()
        if data.get('send'):
            if not data.get('send_subject') or not data.get('send_message'):
                raise ValidationError(
                    _('If vouchers should be sent by email, subject and message need to be specified.')
                )
            if data.get('email') in (None, 'empty'):
                raise ValidationError(
                    _('Please select the CSV column for the recipient email address.')
                )
        return data
