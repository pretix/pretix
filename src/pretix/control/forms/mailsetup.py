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
import ipaddress
import socket

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from pretix.base.forms import SecretKeySettingsField, SettingsForm


class SMTPMailForm(SettingsForm):
    mail_from = forms.EmailField(
        label=_("Sender address"),
        help_text=_("Sender address for outgoing emails"),
        required=True,
    )
    smtp_host = forms.CharField(
        label=_("Hostname"),
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'mail.example.org'})
    )
    smtp_port = forms.IntegerField(
        label=_("Port"),
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. 587, 465, 25, ...'})
    )
    smtp_username = forms.CharField(
        label=_("Username"),
        widget=forms.TextInput(attrs={'placeholder': 'myuser@example.org'}),
        required=False
    )
    smtp_password = SecretKeySettingsField(
        label=_("Password"),
        required=False,
    )
    smtp_use_tls = forms.BooleanField(
        label=_("Use STARTTLS"),
        help_text=_("Commonly enabled on port 587."),
        required=False
    )
    smtp_use_ssl = forms.BooleanField(
        label=_("Use SSL"),
        help_text=_("Commonly enabled on port 465."),
        required=False
    )

    def clean(self):
        data = super().clean()
        if data.get('smtp_use_tls') and data.get('smtp_use_ssl'):
            raise ValidationError(_('You can activate either SSL or STARTTLS security, but not both at the same time.'))
        for k, v in self.fields.items():
            val = data.get(k)
            if v._required and not val:
                self.add_error(k, _('This field is required.'))
        return data

    def clean_smtp_host(self):
        v = self.cleaned_data['smtp_host']
        if not settings.MAIL_CUSTOM_SMTP_ALLOW_PRIVATE_NETWORKS:
            try:
                if ipaddress.ip_address(v).is_private:
                    raise ValidationError(_('You are not allowed to use this mail server, please choose one with a '
                                            'public IP address instead.'))
            except ValueError:
                try:
                    if ipaddress.ip_address(socket.gethostbyname(v)).is_private:
                        raise ValidationError(_('You are not allowed to use this mail server, please choose one with a '
                                                'public IP address instead.'))
                except OSError:
                    raise ValidationError(_('We were unable to resolve this hostname.'))
        return v

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.obj.settings.mail_from in (settings.MAIL_FROM, settings.MAIL_FROM_ORGANIZERS):
            self.initial.pop('mail_from')

        for k, v in self.fields.items():
            v._required = v.required
            v.required = False
            v.widget.is_required = False


class SimpleMailForm(SettingsForm):
    mail_from = forms.EmailField(
        label=_("Sender address"),
        help_text=_("Sender address for outgoing emails"),
        required=True,
    )

    def clean(self):
        cleaned_data = super().clean()
        for k, v in self.fields.items():
            val = cleaned_data.get(k)
            if v._required and not val:
                self.add_error(k, _('This field is required.'))
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.obj.settings.mail_from in (settings.MAIL_FROM, settings.MAIL_FROM_ORGANIZERS):
            self.initial.pop('mail_from')

        for k, v in self.fields.items():
            v._required = v.required
            v.required = False
            v.widget.is_required = False
