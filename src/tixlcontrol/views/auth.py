from django.shortcuts import render, redirect
from django.contrib.auth.forms import AuthenticationForm as BaseAuthenticationForm
from django import forms
from django.utils.translation import ugettext as _
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login


class AuthenticationForm(BaseAuthenticationForm):
    """
    The login form.
    """
    email = forms.EmailField(label=_("E-mail address"), max_length=254)
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput)
    username = None

    error_messages = {
        'invalid_login': _("Please enter a correct e-mail address and password."),
        'inactive': _("This account is inactive."),
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
                    code='invalid_login',
                )
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


def login(request):
    ctx = {}
    if request.user.is_authenticated():
        return redirect('control:index')
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid() and form.user_cache:
            auth_login(request, form.user_cache)
            return redirect('control:index')
    else:
        form = AuthenticationForm()
    ctx['form'] = form
    return render(request, 'tixlcontrol/auth/login.html', ctx)
