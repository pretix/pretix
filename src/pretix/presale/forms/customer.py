from django import forms
from django.contrib.auth.password_validation import (
    password_validators_help_texts, validate_password,
)
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms.questions import NamePartsFormField
from pretix.base.models import Customer


class AuthenticationForm(forms.Form):
    email = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={'autofocus': True})
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )

    error_messages = {
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
                u = self.request.organizer.customers.get(email=email)
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
    name_parts = forms.CharField()
    email = forms.EmailField(
        label=_("Email"),
    )

    error_messages = {
        'duplicate': _(
            "An account with this email address is already registered. Please try to log in or reset your password "
            "instead."
        ),
    }

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

    def clean(self):
        email = self.cleaned_data.get('email')

        if email is not None:
            try:
                self.request.organizer.customers.get(email=email)
            except Customer.DoesNotExist:
                pass
            else:
                raise forms.ValidationError(
                    self.error_messages['duplicate'],
                    code='duplicate',
                )

        return self.cleaned_data


class SetPasswordForm(forms.Form):
    error_messages = {
        'pw_mismatch': _("Please enter the same password twice"),
    }
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput,
        required=True
    )
    password_repeat = forms.CharField(
        label=_('Repeat password'),
        widget=forms.PasswordInput
    )

    def __init__(self, customer=None, *args, **kwargs):
        self.customer = customer
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
    error_messages = {
        'unknown': _("A user with this email address is now known in our system."),
    }
    email = forms.EmailField(
        label=_('Email'),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

    def clean_email(self):
        if 'email' not in self.cleaned_data:
            return
        try:
            self.customer = self.request.organizer.customers.get(email=self.cleaned_data['email'])
            return self.customer.email
        except Customer.DoesNotExist:
            # Yup, this is an information leak. But it prevents dozens of support requests – and even if we didn't
            # have it, there'd be an info leak in the registration flow (trying to sign up for an account, which fails
            # if the email address already exists).
            raise forms.ValidationError(self.error_messages['unknown'], code='unknown')
