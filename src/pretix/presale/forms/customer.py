from django import forms
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Customer


class AuthenticationForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'autofocus': True}))
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
        'unverified': _("You have not yet verified your email address. Please click the link in the email we sent "
                        "you."),
    }

    def __init__(self, request=None, *args, **kwargs):
        """
        The 'request' parameter is set for custom auth use by subclasses.
        The form data comes in via the standard 'data' kwarg.
        """
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
