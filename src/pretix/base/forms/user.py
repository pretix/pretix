from django import forms
from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import (
    password_validators_help_texts, validate_password,
)
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from pytz import common_timezones

from pretix.base.models import User
from pretix.control.forms import SingleLanguageWidget


class UserSettingsForm(forms.ModelForm):
    error_messages = {
        'duplicate_identifier': _("There already is an account associated with this e-mail address. "
                                  "Please choose a different one."),
        'pw_current': _("Please enter your current password if you want to change your e-mail "
                        "address or password."),
        'pw_current_wrong': _("The current password you entered was not correct."),
        'pw_mismatch': _("Please enter the same password twice"),
    }

    old_pw = forms.CharField(max_length=255,
                             required=False,
                             label=_("Your current password"),
                             widget=forms.PasswordInput())
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
            'email'
        ]
        widgets = {
            'locale': SingleLanguageWidget
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        if self.user.auth_backend != 'native':
            del self.fields['old_pw']
            del self.fields['new_pw']
            del self.fields['new_pw_repeat']
            self.fields['email'].disabled = True

    def clean_old_pw(self):
        old_pw = self.cleaned_data.get('old_pw')
        if old_pw and not check_password(old_pw, self.user.password):
            raise forms.ValidationError(
                self.error_messages['pw_current_wrong'],
                code='pw_current_wrong',
            )

        return old_pw

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
        if password1 and validate_password(password1, user=self.user) is not None:
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
        email = self.cleaned_data.get('email')
        old_pw = self.cleaned_data.get('old_pw')

        if (password1 or email != self.user.email) and not old_pw:
            raise forms.ValidationError(
                self.error_messages['pw_current'],
                code='pw_current'
            )

        if password1:
            self.instance.set_password(password1)

        return self.cleaned_data


class User2FADeviceAddForm(forms.Form):
    name = forms.CharField(label=_('Device name'), max_length=64)
    devicetype = forms.ChoiceField(label=_('Device type'), widget=forms.RadioSelect, choices=(
        ('totp', _('Smartphone with the Authenticator application')),
        ('webauthn', _('WebAuthn-compatible hardware token (e.g. Yubikey)')),
    ))
