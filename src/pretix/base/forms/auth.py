from django import forms
from django.conf import settings
from django.contrib.auth.password_validation import (
    password_validators_help_texts, validate_password,
)
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import User


class LoginForm(forms.Form):
    """
    Base class for authenticating users. Extend this to get a form that accepts
    username/password logins.
    """
    keep_logged_in = forms.BooleanField(label=_("Keep me logged in"), required=False)

    error_messages = {
        'invalid_login': _("This combination of credentials is not known to our system."),
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

        if not settings.PRETIX_LONG_SESSIONS:
            del self.fields['keep_logged_in']
        else:
            self.fields.move_to_end('keep_logged_in')

    def clean(self):
        self.user_cache = self.backend.form_authenticate(self.request, self.cleaned_data)
        if self.user_cache is None:
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
        required=True
    )
    password_repeat = forms.CharField(
        label=_('Repeat password'),
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password'  # see https://bugs.chromium.org/p/chromium/issues/detail?id=370363#c7
        }),
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
        required=True
    )
    password_repeat = forms.CharField(
        label=_('Repeat password'),
        widget=forms.PasswordInput
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
        super().__init__(*args, **kwargs)
        for k, f in backend.login_form_fields.items():
            self.fields[k] = f
        if 'email' in self.fields:
            self.fields['email'].disabled = True

    def clean(self):
        self.cleaned_data['email'] = self.user.email
        user_cache = self.backend.form_authenticate(self.request, self.cleaned_data)
        print(user_cache, self.user)
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
