from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import \
    AuthenticationForm as BaseAuthenticationForm
from django.utils.translation import ugettext as _

from pretix.base.models import User


class AuthenticationForm(BaseAuthenticationForm):
    """
    The login form, providing an email and password field. The form already implements
    validation for correct user data.
    """
    email = forms.EmailField(label=_("Email address"), max_length=254)
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput)
    username = None

    error_messages = {
        'invalid_login': _("Please enter a correct e-mail address and password."),
        'inactive': _("This account is inactive.")
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super(forms.Form, self).__init__(*args, **kwargs)

    def clean(self):
        email = self.cleaned_data.get('email')
        password = self.cleaned_data.get('password')

        if email and password:
            self.user_cache = authenticate(identifier=email.lower(),
                                           password=password)
            if self.user_cache is None:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login'
                )
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class GlobalRegistrationForm(forms.Form):
    error_messages = {
        'duplicate_email': _("You already registered with that e-mail address, please use the login form."),
        'pw_mismatch': _("Please enter the same password twice")
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
