from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate, login as auth_login, logout as auth_logout,
)
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import redirect, render
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import TemplateView

from pretix.base.forms.auth import (
    LoginForm, PasswordForgotForm, PasswordRecoverForm, RegistrationForm,
)
from pretix.base.models import User
from pretix.base.services.mail import mail
from pretix.helpers.urls import build_absolute_uri


def login(request):
    """
    Render and process a most basic login form. Takes an URL as GET
    parameter "next" for redirection after successful login
    """
    ctx = {}
    if request.user.is_authenticated():
        return redirect(request.GET.get("next", 'control:index'))
    if request.method == 'POST':
        form = LoginForm(data=request.POST)
        if form.is_valid() and form.user_cache:
            auth_login(request, form.user_cache)
            if "next" in request.GET:
                return redirect(request.GET.get("next", 'control:index'))
            return redirect('control:index')
    else:
        form = LoginForm()
    ctx['form'] = form
    return render(request, 'pretixcontrol/auth/login.html', ctx)


def logout(request):
    """
    Log the user out of the current session, then redirect to login page.
    """
    auth_logout(request)
    return redirect('control:auth.login')


def register(request):
    """
    Render and process a basic registration form.
    """
    ctx = {}
    if request.user.is_authenticated():
        return redirect(request.GET.get("next", 'control:index'))
    if request.method == 'POST':
        form = RegistrationForm(data=request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                form.cleaned_data['email'], form.cleaned_data['password'],
                locale=request.LANGUAGE_CODE,
                timezone=request.timezone if hasattr(request, 'timezone') else settings.TIME_ZONE
            )
            user = authenticate(email=user.email, password=form.cleaned_data['password'])
            auth_login(request, user)
            return redirect('control:index')
    else:
        form = RegistrationForm()
    ctx['form'] = form
    return render(request, 'pretixcontrol/auth/register.html', ctx)


class Forgot(TemplateView):
    template_name = 'pretixcontrol/auth/forgot.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated():
            return redirect(request.GET.get("next", 'control:index'))
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if self.form.is_valid():
            user = self.form.cleaned_data['user']
            mail(
                user.email, _('Password recovery'), 'pretixcontrol/email/forgot.txt',
                {
                    'user': user,
                    'url': (build_absolute_uri('control:auth.forgot.recover')
                            + '?id=%d&token=%s' % (user.id, default_token_generator.make_token(user)))
                },
                None, locale=user.locale
            )
            messages.success(request, _('We sent you an e-mail containing further instructions.'))
            return redirect('control:auth.forgot')
        else:
            return self.get(request, *args, **kwargs)

    @cached_property
    def form(self):
        return PasswordForgotForm(data=self.request.POST if self.request.method == 'POST' else None)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form
        return context


class Recover(TemplateView):
    template_name = 'pretixcontrol/auth/recover.html'

    error_messages = {
        'invalid': _('You clicked on an invalid link. Please check that you copied the full '
                     'web address into your address bar. Please note that the link is only valid '
                     'for three days and that the link can only be used once.'),
        'unknownuser': _('We were unable to find the user you requested a new password for.')
    }

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated():
            return redirect(request.GET.get("next", 'control:index'))
        try:
            user = User.objects.get(id=self.request.GET.get('id'))
        except User.DoesNotExist:
            return self.invalid('unknownuser')
        if not default_token_generator.check_token(user, self.request.GET.get('token')):
            return self.invalid('invalid')
        return super().get(request, *args, **kwargs)

    def invalid(self, msg):
        messages.error(self.request, self.error_messages[msg])
        return redirect('control:auth.forgot')

    def post(self, request, *args, **kwargs):
        if self.form.is_valid():
            try:
                user = User.objects.get(id=self.request.GET.get('id'))
            except User.DoesNotExist:
                return self.invalid('unknownuser')
            if not default_token_generator.check_token(user, self.request.GET.get('token')):
                return self.invalid('invalid')
            user.set_password(self.form.cleaned_data['password'])
            user.save()
            messages.success(request, _('You can now login using your new password.'))
            return redirect('control:auth.login')
        else:
            return self.get(request, *args, **kwargs)

    @cached_property
    def form(self):
        return PasswordRecoverForm(data=self.request.POST if self.request.method == 'POST' else None)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form
        return context
