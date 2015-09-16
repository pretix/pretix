import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate, login, logout, update_session_auth_hash,
)
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.core.urlresolvers import reverse
from django.db.models import Count
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import TemplateView, UpdateView, View

from pretix.base.forms.auth import (
    LoginForm, PasswordForgotForm, PasswordRecoverForm, RegistrationForm,
)
from pretix.base.forms.user import UserSettingsForm
from pretix.base.models import User
from pretix.base.services.mail import mail
from pretix.helpers.urls import build_absolute_uri
from pretix.presale.views import (
    CartDisplayMixin, EventViewMixin, LoginRequiredMixin,
)
from pretix.presale.views.cart import CartAdd


class EventIndex(EventViewMixin, CartDisplayMixin, TemplateView):
    template_name = "pretixpresale/event/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch all items
        items = self.request.event.items.all().filter(
            active=True
        ).select_related(
            'category',  # for re-grouping
        ).prefetch_related(
            'properties',  # for .get_all_available_variations()
            'quotas', 'variations__quotas', 'quotas__event'  # for .availability()
        ).annotate(quotac=Count('quotas')).filter(
            quotac__gt=0
        ).order_by('category__position', 'category_id', 'position', 'name')

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
                    item.max_price = max([v.price for v in item.available_variations])

        items = [item for item in items if len(item.available_variations) > 0]

        # Regroup those by category
        context['items_by_category'] = sorted(
            [
                # a group is a tuple of a category and a list of items
                (cat, [i for i in items if i.category == cat])
                for cat in set([i.category for i in items])
                # insert categories into a set for uniqueness
                # a set is unsorted, so sort again by category
            ],
            key=lambda group: (group[0].position, group[0].identity) if group[0] is not None else (0, "")
        )

        context['cart'] = self.get_cart() if self.request.user.is_authenticated() else None
        return context


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
            return redirect('presale:event.account',
                            organizer=self.request.event.organizer.slug,
                            event=self.request.event.slug)

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated():
            return self.redirect_to_next()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if request.POST.get('form') == 'login':
            form = self.login_form
            if form.is_valid() and form.user_cache:
                login(request, form.user_cache)
                return self.redirect_to_next()
        elif request.POST.get('form') == 'registration':
            form = self.registration_form
            if form.is_valid():
                user = User.objects.create_user(
                    form.cleaned_data['email'], form.cleaned_data['password'],
                    locale=request.LANGUAGE_CODE,
                    timezone=request.timezone if hasattr(request, 'timezone') else settings.TIME_ZONE
                )
                user = authenticate(email=user.email, password=form.cleaned_data['password'])
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
    def registration_form(self):
        return RegistrationForm(
            data=self.request.POST if self.request.POST.get('form', '') == 'registration' else None
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['login_form'] = self.login_form
        context['registration_form'] = self.registration_form
        return context


class EventForgot(EventViewMixin, TemplateView):
    template_name = 'pretixpresale/event/forgot.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated():
            return redirect('presale:event.orders',
                            organizer=self.request.event.organizer.slug,
                            event=self.request.event.slug)
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
                        'url': build_absolute_uri('presale:event.forgot.recover', kwargs={
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
            return redirect('presale:event.forgot',
                            organizer=self.request.event.organizer.slug,
                            event=self.request.event.slug)
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
        if request.user.is_authenticated():
            return redirect('presale:event.orders',
                            organizer=self.request.event.organizer.slug,
                            event=self.request.event.slug)
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
        return redirect('presale:event.forgot',
                        organizer=self.request.event.organizer.slug,
                        event=self.request.event.slug)

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
                user.save()
                messages.success(request, _('You can now login using your new password.'))
            return redirect('presale:event.checkout.login',
                            organizer=self.request.event.organizer.slug,
                            event=self.request.event.slug)
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
        return redirect('presale:event.index',
                        organizer=self.request.event.organizer.slug,
                        event=self.request.event.slug)


class EventAccount(LoginRequiredMixin, EventViewMixin, TemplateView):
    template_name = 'pretixpresale/event/account.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['orders'] = self.request.user.orders.current.count()
        return context


class EventOrders(LoginRequiredMixin, EventViewMixin, TemplateView):
    template_name = 'pretixpresale/event/orders.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['orders'] = self.request.user.orders.current.all()
        return context


class EventAccountSettings(LoginRequiredMixin, EventViewMixin, UpdateView):
    model = User
    form_class = UserSettingsForm
    template_name = 'pretixpresale/event/account_settings.html'

    def get_object(self, queryset=None):
        return self.request.user

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved. See below for details.'))
        return super().form_invalid(form)

    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        sup = super().form_valid(form)
        update_session_auth_hash(self.request, self.request.user)
        return sup

    def get_success_url(self):
        return reverse('presale:event.account.settings',
                       kwargs={
                           'event': self.request.event.slug,
                           'organizer': self.request.event.organizer.slug,
                       })
