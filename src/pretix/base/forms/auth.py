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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Jason Estibeiro, Lukas Bockstaller, Maico Timmerman,
# Sohalt, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import hashlib
import ipaddress

from django import forms
from django.conf import settings
from django.contrib.auth.password_validation import (
    password_validators_help_texts, validate_password,
)
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretix.base.models import User
from pretix.helpers.dicts import move_to_end
from pretix.helpers.http import get_client_ip


class LoginForm(forms.Form):
    """
    Base class for authenticating users. Extend this to get a form that accepts
    username/password logins.
    """
    keep_logged_in = forms.BooleanField(label=_("Keep me logged in"), required=False)

    error_messages = {
        'invalid_login': _("This combination of credentials is not known to our system."),
        'rate_limit': _("For security reasons, please wait 5 minutes before you try again."),
        'inactive': _("This account is inactive.")
    }

    def __init__(self, backend, request=None, *args, **kwargs):
        """
        The 'request' parameter is set for custom auth use by subclasses.
        The form data comes in via the standard 'data' kwarg.
        """
        self.request = request
        self.user_cache = None
        self.backend = backend
        super().__init__(*args, **kwargs)
        for k, f in backend.login_form_fields.items():
            self.fields[k] = f

        # Authentication backends which use urls cannot have long sessions.
        if not settings.PRETIX_LONG_SESSIONS or backend.url:
            del self.fields['keep_logged_in']
        else:
            move_to_end(self.fields, 'keep_logged_in')

    @cached_property
    def ratelimit_key(self):
        if not settings.HAS_REDIS:
            return None
        client_ip = get_client_ip(self.request)
        if not client_ip:
            return None
        try:
            client_ip = ipaddress.ip_address(client_ip)
        except ValueError:
            # Web server not set up correctly
            return None
        if client_ip.is_private:
            # This is the private IP of the server, web server not set up correctly
            return None
        return 'pretix_login_{}'.format(hashlib.sha1(str(client_ip).encode()).hexdigest())

    def clean(self):
        if all(k in self.cleaned_data for k, f in self.fields.items() if f.required):
            if self.ratelimit_key:
                from django_redis import get_redis_connection
                rc = get_redis_connection("redis")
                cnt = rc.get(self.ratelimit_key)
                if cnt and int(cnt) > 10:
                    raise forms.ValidationError(self.error_messages['rate_limit'], code='rate_limit')
            self.user_cache = self.backend.form_authenticate(self.request, self.cleaned_data)
            if self.user_cache is None:
                if self.ratelimit_key:
                    rc.incr(self.ratelimit_key)
                    rc.expire(self.ratelimit_key, 300)
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login'
                )
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data

    def confirm_login_allowed(self, user: User):
        """
        Controls whether the given User may log in. This is a policy setting,
        independent of end-user authentication. This default behavior is to
        allow login by active users, and reject login by inactive users.

        If the given user cannot log in, this method should raise a
        ``forms.ValidationError``.

        If the given user may log in, this method should return None.
        """
        if not user.is_active:
            raise forms.ValidationError(
                self.error_messages['inactive'],
                code='inactive',
            )

    def get_user(self):
        return self.user_cache


class RegistrationForm(forms.Form):
    error_messages = {
        'duplicate_email': _("You already registered with that email address, please use the login form."),
        'pw_mismatch': _("Please enter the same password twice"),
    }
    email = forms.EmailField(
        label=_('Email address'),
        required=True
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password'  # see https://bugs.chromium.org/p/chromium/issues/detail?id=370363#c7
        }),
        max_length=4096,
        required=True
    )
    password_repeat = forms.CharField(
        label=_('Repeat password'),
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password'  # see https://bugs.chromium.org/p/chromium/issues/detail?id=370363#c7
        }),
        max_length=4096,
        required=True
    )
    keep_logged_in = forms.BooleanField(label=_("Keep me logged in"), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not settings.PRETIX_LONG_SESSIONS:
            del self.fields['keep_logged_in']

    def clean(self):
        password1 = self.cleaned_data.get('password', '')
        password2 = self.cleaned_data.get('password_repeat')

        if password1 and password1 != password2:
            raise forms.ValidationError({
                'password_repeat': self.error_messages['pw_mismatch'],
            }, code='pw_mismatch')
        return self.cleaned_data

    def clean_password(self):
        password1 = self.cleaned_data.get('password', '')
        user = User(email=self.cleaned_data.get('email'))
        if validate_password(password1, user=user) is not None:
            raise forms.ValidationError(_(password_validators_help_texts()), code='pw_invalid')
        return password1

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                self.error_messages['duplicate_email'],
                code='duplicate_email'
            )
        return email


class PasswordRecoverForm(forms.Form):
    error_messages = {
        'pw_mismatch': _("Please enter the same password twice"),
    }
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput,
        max_length=4096,
        required=True
    )
    password_repeat = forms.CharField(
        label=_('Repeat password'),
        widget=forms.PasswordInput,
        max_length=4096,
    )

    def __init__(self, user_id=None, *args, **kwargs):
        self.user_id = user_id
        super().__init__(*args, **kwargs)

    def clean(self):
        password1 = self.cleaned_data.get('password', '')
        password2 = self.cleaned_data.get('password_repeat')

        if password1 and password1 != password2:
            raise forms.ValidationError({
                'password_repeat': self.error_messages['pw_mismatch'],
            }, code='pw_mismatch')

        return self.cleaned_data

    def clean_password(self):
        password1 = self.cleaned_data.get('password', '')
        try:
            user = User.objects.get(id=self.user_id)
        except User.DoesNotExist:
            user = None
        if validate_password(password1, user=user) is not None:
            raise forms.ValidationError(_(password_validators_help_texts()), code='pw_invalid')
        return password1


class PasswordForgotForm(forms.Form):
    email = forms.EmailField(
        label=_('E-mail'),
    )

    def __init__(self, *args, **kwargs):
        if 'event' in kwargs:
            # Backwards compatibility
            del kwargs['event']
        super().__init__(*args, **kwargs)

    def clean_email(self):
        return self.cleaned_data['email']


class ReauthForm(forms.Form):
    error_messages = {
        'invalid_login': _("This combination of credentials is not known to our system."),
        'inactive': _("This account is inactive.")
    }

    def __init__(self, backend, user, request=None, *args, **kwargs):
        """
        The 'request' parameter is set for custom auth use by subclasses.
        The form data comes in via the standard 'data' kwarg.
        """
        self.request = request
        self.user = user
        self.backend = backend
        self.backend.url = backend.authentication_url(self.request)
        super().__init__(*args, **kwargs)
        for k, f in backend.login_form_fields.items():
            self.fields[k] = f
        if 'email' in self.fields:
            self.fields['email'].disabled = True

    def clean(self):
        self.cleaned_data['email'] = self.user.email
        user_cache = self.backend.form_authenticate(self.request, self.cleaned_data)
        if user_cache != self.user:
            raise forms.ValidationError(
                self.error_messages['invalid_login'],
                code='invalid_login'
            )
        else:
            self.confirm_login_allowed(user_cache)

        return self.cleaned_data

    def confirm_login_allowed(self, user: User):
        if not user.is_active:
            raise forms.ValidationError(
                self.error_messages['inactive'],
                code='inactive',
            )
