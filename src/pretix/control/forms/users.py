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
from django.contrib import messages
from django.contrib.auth.password_validation import (
    password_validators_help_texts, validate_password,
)
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from pytz import common_timezones

from pretix.base.models import User
from pretix.base.models.auth import StaffSession


class StaffSessionForm(forms.ModelForm):
    class Meta:
        model = StaffSession
        fields = ['comment']


class UserEditForm(forms.ModelForm):
    error_messages = {
        'duplicate_identifier': _("There already is an account associated with this e-mail address. "
                                  "Please choose a different one."),
        'pw_mismatch': _("Please enter the same password twice"),
    }

    new_pw = forms.CharField(max_length=255,
                             required=False,
                             label=_("New password"),
                             widget=forms.PasswordInput())
    new_pw_repeat = forms.CharField(max_length=255,
                                    required=False,
                                    label=_("Repeat new password"),
                                    widget=forms.PasswordInput())
    timezone = forms.ChoiceField(
        choices=((a, a) for a in common_timezones),
        label=_("Default timezone"),
        help_text=_('Only used for views that are not bound to an event. For all '
                    'event views, the event timezone is used instead.')
    )

    class Meta:
        model = User
        fields = [
            'fullname',
            'locale',
            'timezone',
            'email',
            'require_2fa',
            'is_active',
            'is_staff',
            'needs_password_change',
            'last_login'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['last_login'].disabled = True
        if self.instance and self.instance.auth_backend != 'native':
            del self.fields['new_pw']
            del self.fields['new_pw_repeat']
            self.fields['email'].disabled = True

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(Q(email__iexact=email) & ~Q(pk=self.instance.pk)).exists():
            raise forms.ValidationError(
                self.error_messages['duplicate_identifier'],
                code='duplicate_identifier',
            )
        return email

    def clean_new_pw(self):
        password1 = self.cleaned_data.get('new_pw', '')
        if password1 and validate_password(password1, user=self.instance) is not None:
            raise forms.ValidationError(
                _(password_validators_help_texts()),
                code='pw_invalid'
            )
        return password1

    def clean_new_pw_repeat(self):
        password1 = self.cleaned_data.get('new_pw')
        password2 = self.cleaned_data.get('new_pw_repeat')
        if password1 and password1 != password2:
            raise forms.ValidationError(
                self.error_messages['pw_mismatch'],
                code='pw_mismatch'
            )

    def clean(self):
        password1 = self.cleaned_data.get('new_pw')

        if password1:
            self.instance.set_password(password1)

        return self.cleaned_data

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved. See below for details.'))
        return super().form_invalid(form)
