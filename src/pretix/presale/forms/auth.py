from django import forms
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.forms import \
    AuthenticationForm as BaseAuthenticationForm
from django.core.validators import RegexValidator
from django.forms import Form
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import User


class LoginForm(BaseAuthenticationForm):
    username = forms.CharField(
        label=_('Username'),
        help_text=(
            _('If you registered for multiple events, your username is your email address.')
            if settings.PRETIX_GLOBAL_REGISTRATION
            else None
        )
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput
    )

    error_messages = {
        'invalid_login': _("Please enter a correct username and password."),
        'inactive': _("This account is inactive."),
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super(forms.Form, self).__init__(*args, **kwargs)

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            if '@' in username:
                identifier = username.lower()
            else:
                identifier = "%s@%s.event.pretix" % (username, self.request.event.identity)
            self.user_cache = authenticate(identifier=identifier,
                                           password=password)
            if self.user_cache is None:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                )
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class GlobalRegistrationForm(forms.Form):
    error_messages = {
        'duplicate_email': _("You already registered with that e-mail address, please use the login form."),
        'pw_mismatch': _("Please enter the same password twice"),
    }
    email = forms.EmailField(
        label=_('Email address'),
        required=True
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput,
        required=True
    )
    password_repeat = forms.CharField(
        label=_('Repeat password'),
        widget=forms.PasswordInput
    )

    def clean(self):
        password1 = self.cleaned_data.get('password')
        password2 = self.cleaned_data.get('password_repeat')

        if password1 and password1 != password2:
            raise forms.ValidationError(
                self.error_messages['pw_mismatch'],
                code='pw_mismatch',
            )

        return self.cleaned_data

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(identifier=email).exists():
            raise forms.ValidationError(
                self.error_messages['duplicate_email'],
                code='duplicate_email',
            )
        return email


class LocalRegistrationForm(forms.Form):
    error_messages = {
        'invalid_username': _("Please only use characters, numbers or ./+/-/_ in your username."),
        'duplicate_username': _("This username is already taken. Please choose a different one."),
        'pw_mismatch': _("Please enter the same password twice"),
    }
    username = forms.CharField(
        label=_('Username'),
        validators=[
            RegexValidator(
                regex='^[a-zA-Z0-9\.+\-_]*$',
                code='invalid_username',
                message=error_messages['invalid_username']
            ),
        ],
        required=True
    )
    email = forms.EmailField(
        label=_('E-mail address'),
        required=False
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput,
        required=True
    )
    password_repeat = forms.CharField(
        label=_('Repeat password'),
        widget=forms.PasswordInput
    )

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.fields['email'].required = request.event.settings.user_mail_required

    def clean(self):
        password1 = self.cleaned_data.get('password')
        password2 = self.cleaned_data.get('password_repeat')

        if password1 and password1 != password2:
            raise forms.ValidationError(
                self.error_messages['pw_mismatch'],
                code='pw_mismatch',
            )

        return self.cleaned_data

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(event=self.request.event, username=username).exists():
            raise forms.ValidationError(
                self.error_messages['duplicate_username'],
                code='duplicate_username',
            )
        return username


class PasswordRecoverForm(Form):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        password1 = self.cleaned_data.get('password')
        password2 = self.cleaned_data.get('password_repeat')

        if password1 and password1 != password2:
            raise forms.ValidationError(
                self.error_messages['pw_mismatch'],
                code='pw_mismatch',
            )

        return self.cleaned_data


class PasswordForgotForm(Form):
    username = forms.CharField(
        label=_('Username or E-mail'),
    )

    def __init__(self, event, *args, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data['username']
        try:
            self.cleaned_data['user'] = User.objects.get(
                identifier=username, event__isnull=True
            )
            return username
        except User.DoesNotExist:
            pass
        try:
            self.cleaned_data['user'] = User.objects.get(
                username=username, event=self.event
            )
            return username
        except User.DoesNotExist:
            pass
        try:
            self.cleaned_data['user'] = User.objects.get(
                email=username, event=self.event
            )
            return username
        except User.MultipleObjectsReturned:
            raise forms.ValidationError(
                _("We found multiple users with that e-mail address. Please specify the username instead"),
                code='unknown_user',
            )
        except User.DoesNotExist:
            raise forms.ValidationError(
                _("We are unable to find a user matching the data you provided."),
                code='unknown_user',
            )
