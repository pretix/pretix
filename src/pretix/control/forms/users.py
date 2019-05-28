from django import forms
from django.contrib import messages
from django.contrib.auth.password_validation import (
    password_validators_help_texts, validate_password,
)
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
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
            'last_login'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['last_login'].disabled = True

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
