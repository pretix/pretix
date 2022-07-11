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
import hashlib
import ipaddress
import random

from django import forms
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import (
    password_validators_help_texts, validate_password,
)
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import signing
from django.utils.functional import cached_property
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _
from phonenumber_field.formfields import PhoneNumberField

from pretix.base.forms.questions import (
    NamePartsFormField, WrappedPhoneNumberPrefixWidget, get_country_by_locale,
    get_phone_prefix,
)
from pretix.base.i18n import get_language_without_region
from pretix.base.models import Customer
from pretix.helpers.http import get_client_ip


class TokenGenerator(PasswordResetTokenGenerator):
    key_salt = "pretix.presale.forms.customer.TokenGenerator"


class AuthenticationForm(forms.Form):
    required_css_class = 'required'
    email = forms.EmailField(
        label=_("E-mail"),
        widget=forms.EmailInput(attrs={'autofocus': True})
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
        max_length=4096,
    )

    error_messages = {
        'incomplete': _('You need to fill out all fields.'),
        'invalid_login': _(
            "We have not found an account with this email address and password."
        ),
        'inactive': _("This account is disabled."),
        'unverified': _("You have not yet activated your account and set a password. Please click the link in the "
                        "email we sent you. Click \"Reset password\" to receive a new email in case you cannot find "
                        "it again."),
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.customer_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        email = self.cleaned_data.get('email')
        password = self.cleaned_data.get('password')

        if email is not None and password:
            try:
                u = self.request.organizer.customers.get(email=email.lower(), provider__isnull=True)
            except Customer.DoesNotExist:
                # Run the default password hasher once to reduce the timing
                # difference between an existing and a nonexistent user (django #20760).
                Customer().set_password(password)
            else:
                if u.check_password(password):
                    self.customer_cache = u
            if self.customer_cache is None:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                )
            else:
                self.confirm_login_allowed(self.customer_cache)
        else:
            raise forms.ValidationError(
                self.error_messages['incomplete'],
                code='incomplete'
            )

        return self.cleaned_data

    def confirm_login_allowed(self, user):
        if not user.is_active:
            raise forms.ValidationError(
                self.error_messages['inactive'],
                code='inactive',
            )
        if not user.is_verified:
            raise forms.ValidationError(
                self.error_messages['unverified'],
                code='unverified',
            )

    def get_customer(self):
        return self.customer_cache


class RegistrationForm(forms.Form):
    required_css_class = 'required'
    name_parts = forms.CharField()
    email = forms.EmailField(
        label=_("E-mail"),
    )

    error_messages = {
        'rate_limit': _("We've received a lot of registration requests from you, please wait 10 minutes before you try again."),
        'duplicate': _(
            "An account with this email address is already registered. Please try to log in or reset your password "
            "instead."
        ),
        'required': _('This field is required.'),
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.standalone = kwargs.pop('standalone')
        self.signer = signing.TimestampSigner(salt=f'customer-registration-captcha-{get_client_ip(request)}')
        super().__init__(*args, **kwargs)

        event = getattr(request, "event", None)
        if event and event.settings.order_phone_asked:
            if event.settings.region or event.organizer.settings.region:
                country_code = event.settings.region or event.organizer.settings.region
                phone_prefix = get_phone_prefix(country_code)
                if phone_prefix:
                    self.initial['phone'] = "+{}.".format(phone_prefix)
            self.fields['phone'] = PhoneNumberField(
                label=_('Phone'),
                required=event.settings.order_phone_required,
                widget=WrappedPhoneNumberPrefixWidget()
            )

        self.fields['name_parts'] = NamePartsFormField(
            max_length=255,
            required=True,
            scheme=request.organizer.settings.name_scheme,
            titles=request.organizer.settings.name_scheme_titles,
            label=_('Name'),
        )

        if self.standalone:
            # In the setandalone registration form, we add a simple CAPTCHA. We don't expect
            # this to actually turn away and motivated attacker, it's mainly a protection
            # against spam bots looking for contact forms. Since the standalone registration
            # form is one of the simplest public forms we have in the application it is the
            # most common target for untargeted bots.
            a = random.randint(1, 9)
            b = random.randint(1, 9)
            if 'challenge' in self.data:
                try:
                    a, b = self.signer.unsign(self.data.get('challenge'), max_age=3600).split('+')
                    a, b = int(a), int(b)
                except:
                    pass
            self.fields['challenge'] = forms.CharField(
                widget=forms.HiddenInput,
                initial=self.signer.sign(f'{a}+{b}')

            )
            self.fields['response'] = forms.IntegerField(
                label=_('What is the result of {num1} + {num2}?').format(
                    num1=a, num2=b,
                ),
                min_value=0,
            )

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
        return 'pretix_customer_registration_{}'.format(hashlib.sha1(str(client_ip).encode()).hexdigest())

    def clean(self):
        email = self.cleaned_data.get('email')

        if email is not None:
            try:
                self.request.organizer.customers.get(email=email.lower())
            except Customer.DoesNotExist:
                pass
            else:
                raise forms.ValidationError(
                    {'email': self.error_messages['duplicate']},
                    code='duplicate',
                )

        if self.standalone:
            expect = -1
            try:
                a, b = self.signer.unsign(self.cleaned_data.get('challenge'), max_age=3600).split('+')
                expect = int(a) + int(b)
            except:
                pass
            if self.cleaned_data.get('response') != expect:
                raise forms.ValidationError(
                    {'response': _('Please enter the correct result.')},
                    code='challenge_invalid'
                )

        if not self.cleaned_data.get('email'):
            raise forms.ValidationError(
                {'email': self.error_messages['required']},
                code='incomplete'
            )
        else:
            if self.ratelimit_key:
                from django_redis import get_redis_connection

                rc = get_redis_connection("redis")
                cnt = rc.incr(self.ratelimit_key)
                rc.expire(self.ratelimit_key, 600)
                if cnt > 10:
                    raise forms.ValidationError(
                        self.error_messages['rate_limit'],
                        code='rate_limit',
                    )
        return self.cleaned_data

    def create(self):
        customer = self.request.organizer.customers.create(
            email=self.cleaned_data['email'],
            name_parts=self.cleaned_data['name_parts'],
            phone=self.cleaned_data.get('phone'),
            is_active=True,
            is_verified=False,
            locale=get_language_without_region(),
        )
        customer.set_unusable_password()
        customer.save()
        customer.log_action('pretix.customer.created', {})
        customer.send_activation_mail()
        return customer


class SetPasswordForm(forms.Form):
    required_css_class = 'required'
    error_messages = {
        'pw_mismatch': _("Please enter the same password twice"),
    }
    email = forms.EmailField(
        label=_('E-mail'),
        disabled=True
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={'minlength': '8', 'autocomplete': 'new-password'}),
        max_length=4096,
        required=True
    )
    password_repeat = forms.CharField(
        label=_('Repeat password'),
        widget=forms.PasswordInput(attrs={'minlength': '8', 'autocomplete': 'new-password'}),
        max_length=4096,
    )

    def __init__(self, customer=None, *args, **kwargs):
        self.customer = customer
        kwargs.setdefault('initial', {})
        kwargs['initial']['email'] = self.customer.email
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
        if validate_password(password1, user=self.customer) is not None:
            raise forms.ValidationError(_(password_validators_help_texts()), code='pw_invalid')
        return password1


class ResetPasswordForm(forms.Form):
    required_css_class = 'required'
    error_messages = {
        'rate_limit': _("For security reasons, please wait 10 minutes before you try again."),
        'unknown': _("A user with this email address is not known in our system."),
    }
    email = forms.EmailField(
        label=_('E-mail'),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

    def clean_email(self):
        if 'email' not in self.cleaned_data:
            return
        try:
            self.customer = self.request.organizer.customers.get(email=self.cleaned_data['email'].lower(), provider__isnull=True)
            return self.customer.email
        except Customer.DoesNotExist:
            # Yup, this is an information leak. But it prevents dozens of support requests – and even if we didn't
            # have it, there'd be an info leak in the registration flow (trying to sign up for an account, which fails
            # if the email address already exists).
            raise forms.ValidationError(self.error_messages['unknown'], code='unknown')

    def clean(self):
        d = super().clean()
        if d.get('email') and settings.HAS_REDIS:
            from django_redis import get_redis_connection

            rc = get_redis_connection("redis")
            cnt = rc.incr('pretix_pwreset_customer_%s' % self.customer.pk)
            rc.expire('pretix_pwreset_customer_%s' % self.customer.pk, 600)
            if cnt > 2:
                raise forms.ValidationError(
                    self.error_messages['rate_limit'],
                    code='rate_limit',
                )
        return d


class ChangePasswordForm(forms.Form):
    required_css_class = 'required'
    error_messages = {
        'pw_current_wrong': _("The current password you entered was not correct."),
        'pw_mismatch': _("Please enter the same password twice"),
        'rate_limit': _("For security reasons, please wait 5 minutes before you try again."),
    }
    email = forms.EmailField(
        label=_('E-mail'),
        disabled=True
    )
    password_current = forms.CharField(
        label=_('Your current password'),
        widget=forms.PasswordInput,
        required=True
    )
    password = forms.CharField(
        label=_('New password'),
        widget=forms.PasswordInput,
        max_length=4096,
        required=True
    )
    password_repeat = forms.CharField(
        label=_('Repeat password'),
        widget=forms.PasswordInput(attrs={'minlength': '8', 'autocomplete': 'new-password'}),
        max_length=4096,
    )

    def __init__(self, customer, *args, **kwargs):
        self.customer = customer
        kwargs.setdefault('initial', {})
        kwargs['initial']['email'] = self.customer.email
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
        if validate_password(password1, user=self.customer) is not None:
            raise forms.ValidationError(_(password_validators_help_texts()), code='pw_invalid')
        return password1

    def clean_password_current(self):
        old_pw = self.cleaned_data.get('password_current')

        if old_pw and settings.HAS_REDIS:
            from django_redis import get_redis_connection

            rc = get_redis_connection("redis")
            cnt = rc.incr('pretix_pwchange_customer_%s' % self.customer.pk)
            rc.expire('pretix_pwchange_customer_%s' % self.customer.pk, 300)
            if cnt > 10:
                raise forms.ValidationError(
                    self.error_messages['rate_limit'],
                    code='rate_limit',
                )

        if old_pw and not check_password(old_pw, self.customer.password):
            raise forms.ValidationError(
                self.error_messages['pw_current_wrong'],
                code='pw_current_wrong',
            )


class ChangeInfoForm(forms.ModelForm):
    required_css_class = 'required'
    error_messages = {
        'pw_current_wrong': _("The current password you entered was not correct."),
        'rate_limit': _("For security reasons, please wait 5 minutes before you try again."),
        'duplicate': _("An account with this email address is already registered."),
    }
    password_current = forms.CharField(
        label=_('Your current password'),
        widget=forms.PasswordInput,
        help_text=_('Only required if you change your email address'),
        max_length=4096,
        required=False
    )

    class Meta:
        model = Customer
        fields = ('name_parts', 'email', 'phone')

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

        self.fields['name_parts'] = NamePartsFormField(
            max_length=255,
            required=True,
            scheme=request.organizer.settings.name_scheme,
            titles=request.organizer.settings.name_scheme_titles,
            label=_('Name'),
        )

        if not self.initial.get('phone') and (request.organizer.settings.region or self.instance.locale):
            country_code = self.instance.organizer.settings.region or get_country_by_locale(self.instance.locale)
            phone_prefix = get_phone_prefix(country_code)
            if phone_prefix:
                self.initial['phone'] = "+{}.".format(phone_prefix)

        self.fields['phone'] = PhoneNumberField(
            label=_('Phone'),
            required=False,
            widget=WrappedPhoneNumberPrefixWidget()
        )

        if self.instance.provider_id is not None:
            self.fields['email'].disabled = True
            self.fields['email'].help_text = _(
                'To change your email address, change it in your {provider} account and then log out and log in '
                'again.'
            ).format(provider=escape(self.instance.provider.name))
            del self.fields['password_current']

    def clean_password_current(self):
        old_pw = self.cleaned_data.get('password_current')

        if old_pw:
            if settings.HAS_REDIS:
                from django_redis import get_redis_connection

                rc = get_redis_connection("redis")
                cnt = rc.incr('pretix_pwchange_customer_%s' % self.instance.pk)
                rc.expire('pretix_pwchange_customer_%s' % self.instance.pk, 300)
                if cnt > 10:
                    raise forms.ValidationError(
                        self.error_messages['rate_limit'],
                        code='rate_limit',
                    )

            if not check_password(old_pw, self.instance.password):
                raise forms.ValidationError(
                    self.error_messages['pw_current_wrong'],
                    code='pw_current_wrong',
                )

            return "***valid***"

    def clean(self):
        email = self.cleaned_data.get('email')
        password_current = self.cleaned_data.get('password_current')

        if email != self.instance.email and not password_current and self.instance.provider_id is None:
            raise forms.ValidationError(
                self.error_messages['pw_current_wrong'],
                code='pw_current_wrong',
            )

        if email is not None and self.instance.provider_id is not None:
            try:
                self.request.organizer.customers.exclude(pk=self.instance.pk).get(email=email.lower())
            except Customer.DoesNotExist:
                pass
            else:
                raise forms.ValidationError(
                    self.error_messages['duplicate'],
                    code='duplicate',
                )

        return self.cleaned_data
