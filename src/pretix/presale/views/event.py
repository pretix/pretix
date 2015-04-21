import json
from django.contrib import messages
from django.contrib.auth import authenticate, logout
from django.core import signing
from django.core.signing import SignatureExpired, BadSignature
from django.core.urlresolvers import reverse
from django.core.validators import RegexValidator
from django.db.models import Count
from django import forms
from django.forms import Form
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.contrib.auth.forms import AuthenticationForm as BaseAuthenticationForm
from django.contrib.auth import login
from django.views.generic import TemplateView, View
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from pretix.base.mail import mail
from pretix.base.models import User

from pretix.presale.views import EventViewMixin, CartDisplayMixin, EventLoginRequiredMixin
from pretix.presale.views.cart import CartAdd


class EventIndex(EventViewMixin, CartDisplayMixin, TemplateView):
    template_name = "pretixpresale/event/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch all items
        items = self.request.event.items.all().select_related(
            'category',  # for re-grouping
        ).prefetch_related(
            'properties',  # for .get_all_available_variations()
            'quotas', 'variations__quotas', 'quotas__event'  # for .availability()
        ).annotate(quotac=Count('quotas')).filter(
            quotac__gt=0
        ).order_by('category__position', 'category_id', 'name')

        for item in items:
            item.available_variations = sorted(item.get_all_available_variations(),
                                               key=lambda vd: vd.ordered_values())
            item.has_variations = (len(item.available_variations) != 1
                                   or not item.available_variations[0].empty())
            if not item.has_variations:
                item.cached_availability = list(item.check_quotas())
                item.cached_availability[1] = min(item.cached_availability[1],
                                                  int(self.request.event.settings.max_items_per_order))
                item.price = item.available_variations[0]['price']
            else:
                for var in item.available_variations:
                    var.cached_availability = list(var['variation'].check_quotas())
                    var.cached_availability[1] = min(var.cached_availability[1],
                                                     int(self.request.event.settings.max_items_per_order))
                    var.price = var.get('price', item.default_price)
                if len(item.available_variations) > 0:
                    item.min_price = min([v.price for v in item.available_variations])

        items = [item for item in items if len(item.available_variations) > 0]

        # Regroup those by category
        context['items_by_category'] = sorted([
            # a group is a tuple of a category and a list of items
            (cat, [i for i in items if i.category == cat])
            for cat in set([i.category for i in items])  # insert categories into a set for uniqueness
            # a set is unsorted, so sort again by category
        ], key=lambda group: (group[0].position, group[0].identity) if group[0] is not None else (0, ""))

        context['cart'] = self.get_cart() if self.request.user.is_authenticated() else None
        return context


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


class EventLogin(EventViewMixin, TemplateView):
    template_name = 'pretixpresale/event/login.html'

    def redirect_to_next(self):
        if 'cart_tmp' in self.request.session and self.request.user.is_authenticated():
            items = json.loads(self.request.session['cart_tmp'])
            del self.request.session['cart_tmp']
            ca = CartAdd()
            ca.request = self.request
            ca.items = items
            return ca.process()
        if 'next' in self.request.GET:
            return redirect(self.request.GET.get('next'))
        else:
            return redirect(reverse(
                'presale:event.orders', kwargs={
                    'organizer': self.request.event.organizer.slug,
                    'event': self.request.event.slug,
                }
            ))

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated() and \
                (request.user.event is None or request.user.event == request.event):
            return self.redirect_to_next()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if request.POST.get('form') == 'login':
            form = self.login_form
            if form.is_valid() and form.user_cache:
                login(request, form.user_cache)
                return self.redirect_to_next()
        elif request.POST.get('form') == 'local_registration':
            form = self.local_registration_form
            if form.is_valid():
                user = User.objects.create_local_user(
                    request.event, form.cleaned_data['username'], form.cleaned_data['password'],
                    email=form.cleaned_data['email'] if form.cleaned_data['email'] != '' else None
                )
                user = authenticate(identifier=user.identifier, password=form.cleaned_data['password'])
                login(request, user)
                return self.redirect_to_next()
        elif request.POST.get('form') == 'global_registration' and settings.PRETIX_GLOBAL_REGISTRATION:
            form = self.global_registration_form
            if form.is_valid():
                user = User.objects.create_global_user(
                    form.cleaned_data['email'], form.cleaned_data['password'],
                    )
                user = authenticate(identifier=user.identifier, password=form.cleaned_data['password'])
                login(request, user)
                return self.redirect_to_next()
        return super().get(request, *args, **kwargs)

    @cached_property
    def login_form(self):
        return LoginForm(
            self.request,
            data=self.request.POST if self.request.POST.get('form', '') == 'login' else None
        )

    @cached_property
    def global_registration_form(self):
        if settings.PRETIX_GLOBAL_REGISTRATION:
            return GlobalRegistrationForm(
                data=self.request.POST if self.request.POST.get('form', '') == 'global_registration' else None
            )
        else:
            return None

    @cached_property
    def local_registration_form(self):
        return LocalRegistrationForm(
            self.request,
            data=self.request.POST if self.request.POST.get('form', '') == 'local_registration' else None
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['login_form'] = self.login_form
        context['global_registration_form'] = self.global_registration_form
        context['local_registration_form'] = self.local_registration_form
        return context


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
        except:
            raise forms.ValidationError(
                _("We are unable to find a user matching the data you provided."),
                code='unknown_user',
            )


class EventForgot(EventViewMixin, TemplateView):
    template_name = 'pretixpresale/event/forgot.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated() and \
                (request.user.event is None or request.user.event == request.event):
            return redirect(reverse(
                'presale:event.orders', kwargs={
                    'organizer': self.request.event.organizer.slug,
                    'event': self.request.event.slug,
                    }
            ))
        return super().get(request, *args, **kwargs)

    def generate_token(self, user):
        return signing.dumps({
            "type": "reset",
            "user": user.id
        })

    def post(self, request, *args, **kwargs):
        if self.form.is_valid():
            user = self.form.cleaned_data['user']
            if user.email:
                mail(
                    user, _('Password recovery'),
                    'pretixpresale/email/forgot.txt',
                    {
                        'user': user,
                        'event': self.request.event,
                        'url': settings.SITE_URL + reverse('presale:event.forgot.recover', kwargs={
                            'event': self.request.event.slug,
                            'organizer': self.request.event.organizer.slug,
                            }) + '?token=' + self.generate_token(user),
                        },
                    self.request.event
                )
                messages.success(request, _('We sent you an e-mail containing further instructions.'))
            else:
                messages.success(request, _('We are unable to send you a new password, as you did not enter an e-mail '
                                            'address at your registration.'))
            return redirect(reverse(
                'presale:event.forgot', kwargs={
                    'organizer': self.request.event.organizer.slug,
                    'event': self.request.event.slug,
                    }
            ))
        else:
            return self.get(request, *args, **kwargs)

    @cached_property
    def form(self):
        return PasswordForgotForm(
            event=self.request.event,
            data=self.request.POST if self.request.method == 'POST' else None
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form
        return context


class EventRecover(EventViewMixin, TemplateView):
    template_name = 'pretixpresale/event/recover.html'

    error_messages = {
        'invalid': _('You clicked on an invalid link. Please check that you copied the full '
                     'web address into your address bar.'),
        'expired': _('This password recovery link has expired. Please request a new e-mail and '
                     'use the recovery link within 24 hours.'),
        'unknownuser': _('We were unable to find the user you requested a new password for.')
    }

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated() and \
                (request.user.event is None or request.user.event == request.event):
            return redirect(reverse(
                'presale:event.orders', kwargs={
                    'organizer': self.request.event.organizer.slug,
                    'event': self.request.event.slug,
                }
            ))
        try:
            self.get_user()
        except User.DoesNotExist:
            return self.invalid('unknownuser')
        except SignatureExpired:
            return self.invalid('expired')
        except BadSignature:
            return self.invalid('invalid')
        return super().get(request, *args, **kwargs)

    def get_user(self):
        token = signing.loads(self.request.GET.get('token', ''),
                              max_age=3600 * 24)
        if token['type'] != 'reset':
            raise BadSignature()
        return User.objects.get(id=token['user'])

    def invalid(self, msg):
        messages.error(self.request, self.error_messages[msg])
        return redirect(reverse(
            'presale:event.forgot', kwargs={
                'organizer': self.request.event.organizer.slug,
                'event': self.request.event.slug
            }
        ))

    def post(self, request, *args, **kwargs):
        if self.form.is_valid():
            try:
                user = self.get_user()
            except User.DoesNotExist:
                return self.invalid('unknownuser')
            except SignatureExpired:
                return self.invalid('expired')
            except BadSignature:
                return self.invalid('invalid')
            else:
                user.set_password(self.form.cleaned_data['password'])
                messages.success(request, _('You can now login using your new password.'))
            return redirect(reverse(
                'presale:event.checkout.login', kwargs={
                    'organizer': self.request.event.organizer.slug,
                    'event': self.request.event.slug,
                }
            ))
        else:
            return self.get(request, *args, **kwargs)

    @cached_property
    def form(self):
        return PasswordRecoverForm(
            data=self.request.POST if self.request.method == 'POST' else None
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form
        return context


class EventLogout(EventViewMixin, View):
    def get(self, request, *args, **kwargs):
        logout(request)
        return redirect(reverse(
            'presale:event.index', kwargs={
                'organizer': self.request.event.organizer.slug,
                'event': self.request.event.slug,
            }
        ))


class EventOrders(EventLoginRequiredMixin, EventViewMixin, TemplateView):
    template_name = 'pretixpresale/event/orders.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['orders'] = self.request.user.orders.current.all()
        return context
