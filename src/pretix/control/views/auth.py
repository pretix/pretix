from django.conf import settings
from django.contrib.auth import (
    authenticate, login as auth_login, logout as auth_logout,
)
from django.shortcuts import redirect, render

from pretix.base.forms.auth import LoginForm, RegistrationForm
from pretix.base.models import User


def login(request):
    """
    Render and process a most basic login form. Takes an URL as GET
    parameter "next" for redirection after successful login
    """
    ctx = {}
    if request.user.is_authenticated():
        if "next" in request.GET:
            return redirect(request.GET.get("next", 'control:index'))
        return redirect('control:index')
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
        if "next" in request.GET:
            return redirect(request.GET.get("next", 'control:index'))
        return redirect('control:index')
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
