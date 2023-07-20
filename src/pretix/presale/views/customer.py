#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import hashlib
import re
from importlib import import_module
from urllib.parse import (
    parse_qs, quote, urlencode, urljoin, urlparse, urlsplit, urlunparse,
)

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.signing import BadSignature, dumps, loads
from django.db import IntegrityError, transaction
from django.db.models import (
    Count, IntegerField, OuterRef, Prefetch, Q, Subquery,
)
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import FormView, ListView, View

from pretix.base.customersso.oidc import (
    oidc_authorize_url, oidc_validate_authorization,
)
from pretix.base.models import Customer, InvoiceAddress, Order, OrderPosition
from pretix.base.services.mail import mail
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.base.signals import customer_created, customer_signed_in
from pretix.helpers.compat import CompatDeleteView
from pretix.helpers.http import redirect_to_url
from pretix.multidomain.models import KnownDomain
from pretix.multidomain.urlreverse import build_absolute_uri, eventreverse
from pretix.presale.forms.customer import (
    AuthenticationForm, ChangeInfoForm, ChangePasswordForm, RegistrationForm,
    ResetPasswordForm, SetPasswordForm, TokenGenerator,
)
from pretix.presale.utils import (
    customer_login, customer_logout, update_customer_session_auth_hash,
)

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore


class RedirectBackMixin:
    redirect_field_name = 'next'

    def get_redirect_url(self, redirect_to=None):
        """Return the user-originating redirect URL if it's safe."""
        redirect_to = redirect_to or self.request.POST.get(
            self.redirect_field_name,
            self.request.GET.get(self.redirect_field_name, '')
        )
        hosts = list(KnownDomain.objects.filter(event__organizer=self.request.organizer).values_list('domainname', flat=True))
        siteurlsplit = urlsplit(settings.SITE_URL)
        if siteurlsplit.port and siteurlsplit.port not in (80, 443):
            hosts = ['%s:%d' % (h, siteurlsplit.port) for h in hosts]

        url_is_safe = url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts=hosts,
            require_https=self.request.is_secure(),
        )
        return redirect_to if url_is_safe else ''


class LoginView(RedirectBackMixin, FormView):
    """
    Display the login form and handle the login action.
    """
    form_class = AuthenticationForm
    template_name = 'pretixpresale/organizers/customer_login.html'
    redirect_authenticated_user = True

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts:
            raise Http404('Feature not enabled')
        if self.redirect_authenticated_user and self.request.customer:
            redirect_to = self.get_success_url()
            if redirect_to == self.request.path:
                raise ValueError(
                    "Redirection loop for authenticated user detected. Check that "
                    "your LOGIN_REDIRECT_URL doesn't point to a login page."
                )
            return HttpResponseRedirect(redirect_to)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts_native:
            raise Http404('Feature not enabled')
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **kwargs,
            providers=self.request.organizer.sso_providers.all()
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def get_success_url(self):
        url = self.get_redirect_url()

        if not url:
            return eventreverse(self.request.organizer, 'presale:organizer.customer.profile', kwargs={})

        if self.request.GET.get("request_cross_domain_customer_auth") == "true":
            otpstore = SessionStore()
            otpstore[f'customer_cross_domain_auth_{self.request.organizer.pk}'] = self.request.session.session_key
            otpstore.set_expiry(60)
            otpstore.save(must_create=True)
            otp = otpstore.session_key

            u = urlparse(url)
            qsl = parse_qs(u.query)
            qsl['cross_domain_customer_auth'] = otp
            url = urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(qsl, doseq=True), u.fragment))

        return url

    def form_valid(self, form):
        """Security check complete. Log the user in."""
        customer = form.get_customer()
        customer_login(self.request, customer)
        customer_signed_in.send(customer.organizer, customer=customer)
        return HttpResponseRedirect(self.get_success_url())


class LogoutView(View):
    redirect_field_name = 'next'

    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        customer_logout(request)
        next_page = self.get_next_page()
        return HttpResponseRedirect(next_page)

    def get_next_page(self):
        if getattr(self.request, 'event_domain', False):
            # After we cleared the cookies on this domain, redirect to the parent domain to clear cookies as well
            next_page = eventreverse(self.request.organizer, 'presale:organizer.customer.logout', kwargs={})
            if self.redirect_field_name in self.request.POST or self.redirect_field_name in self.request.GET:
                after_next_page = self.request.POST.get(
                    self.redirect_field_name,
                    self.request.GET.get(self.redirect_field_name)
                )
                next_page += '?' + urlencode({
                    'next': urljoin(f'{self.request.scheme}://{self.request.get_host()}', after_next_page)
                })
        else:
            next_page = eventreverse(self.request.organizer, 'presale:organizer.index', kwargs={})

            if (self.redirect_field_name in self.request.POST or
                    self.redirect_field_name in self.request.GET):
                next_page = self.request.POST.get(
                    self.redirect_field_name,
                    self.request.GET.get(self.redirect_field_name)
                )
                hosts = list(KnownDomain.objects.filter(event__organizer=self.request.organizer).values_list('domainname', flat=True))
                siteurlsplit = urlsplit(settings.SITE_URL)
                if siteurlsplit.port and siteurlsplit.port not in (80, 443):
                    hosts = ['%s:%d' % (h, siteurlsplit.port) for h in hosts]
                url_is_safe = url_has_allowed_host_and_scheme(
                    url=next_page,
                    allowed_hosts=hosts,
                    require_https=self.request.is_secure(),
                )
                # Security check -- Ensure the user-originating redirection URL is
                # safe.
                if not url_is_safe:
                    next_page = self.request.path

        return next_page


class RegistrationView(RedirectBackMixin, FormView):
    form_class = RegistrationForm
    template_name = 'pretixpresale/organizers/customer_registration.html'
    redirect_authenticated_user = True

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts:
            raise Http404('Feature not enabled')
        if not request.organizer.settings.customer_accounts_native:
            raise Http404('Feature not enabled')
        if self.redirect_authenticated_user and self.request.customer:
            redirect_to = self.get_success_url()
            if redirect_to == self.request.path:
                raise ValueError(
                    "Redirection loop for authenticated user detected. Check that "
                    "your LOGIN_REDIRECT_URL doesn't point to a login page."
                )
            return HttpResponseRedirect(redirect_to)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        kwargs['standalone'] = True
        return kwargs

    def get_success_url(self):
        url = self.get_redirect_url()
        return url or eventreverse(self.request.organizer, 'presale:organizer.customer.login', kwargs={})

    def form_valid(self, form):
        with transaction.atomic():
            customer = form.create()
            customer_created.send(customer.organizer, customer=customer)
        messages.success(
            self.request,
            _('Your account has been created. Please follow the link in the email we sent you to activate your '
              'account and choose a password.')
        )
        return HttpResponseRedirect(self.get_success_url())


class SetPasswordView(FormView):
    form_class = SetPasswordForm
    template_name = 'pretixpresale/organizers/customer_setpassword.html'

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts:
            raise Http404('Feature not enabled')
        if not request.organizer.settings.customer_accounts_native:
            raise Http404('Feature not enabled')
        try:
            self.customer = request.organizer.customers.get(identifier=self.request.GET.get('id'), provider__isnull=True)
        except Customer.DoesNotExist:
            messages.error(request, _('You clicked an invalid link.'))
            return HttpResponseRedirect(self.get_success_url())
        if not TokenGenerator().check_token(self.customer, self.request.GET.get('token', '')):
            messages.error(request, _('You clicked an invalid link.'))
            return HttpResponseRedirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['customer'] = self.customer
        return kwargs

    def get_success_url(self):
        return eventreverse(self.request.organizer, 'presale:organizer.customer.login', kwargs={})

    def form_valid(self, form):
        with transaction.atomic():
            self.customer.set_password(form.cleaned_data['password'])
            self.customer.is_verified = True
            self.customer.save()
            self.customer.log_action('pretix.customer.password.set', {})
        messages.success(
            self.request,
            _('Your new password has been set! You can now use it to log in.'),
        )
        return HttpResponseRedirect(self.get_success_url())


class ResetPasswordView(FormView):
    form_class = ResetPasswordForm
    template_name = 'pretixpresale/organizers/customer_resetpw.html'

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts:
            raise Http404('Feature not enabled')
        if not request.organizer.settings.customer_accounts_native:
            raise Http404('Feature not enabled')
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return eventreverse(self.request.organizer, 'presale:organizer.customer.login', kwargs={})

    def form_valid(self, form):
        customer = form.customer
        customer.log_action('pretix.customer.password.resetrequested', {})
        ctx = customer.get_email_context()
        token = TokenGenerator().make_token(customer)
        ctx['url'] = build_absolute_uri(self.request.organizer,
                                        'presale:organizer.customer.recoverpw') + '?id=' + customer.identifier + '&token=' + token
        mail(
            customer.email,
            self.request.organizer.settings.mail_subject_customer_reset,
            self.request.organizer.settings.mail_text_customer_reset,
            ctx,
            locale=customer.locale,
            customer=customer,
            organizer=self.request.organizer,
        )
        messages.success(
            self.request,
            _('We\'ve sent you an email with further instructions on resetting your password.')
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs


class CustomerRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts:
            raise Http404('Feature not enabled')
        if not getattr(request, 'customer', None):
            return redirect(
                eventreverse(self.request.organizer, 'presale:organizer.customer.login', kwargs={}) +
                '?next=' + quote(self.request.path_info + '?' + self.request.GET.urlencode())
            )
        return super().dispatch(request, *args, **kwargs)


class ProfileView(CustomerRequiredMixin, ListView):
    template_name = 'pretixpresale/organizers/customer_profile.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        q = Q(customer=self.request.customer)
        if self.request.organizer.settings.customer_accounts_link_by_email and self.request.customer.email:
            # This is safe because we only let customers with verified emails log in
            q |= Q(email__iexact=self.request.customer.email)
        qs = Order.objects.filter(
            q
        ).prefetch_related(
            Prefetch('event', queryset=self.request.organizer.events.prefetch_related('_settings_objects'))
        ).order_by('-datetime')
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['customer'] = self.request.customer
        ctx['memberships'] = self.request.customer.memberships.with_usages().select_related(
            'membership_type', 'granted_in', 'granted_in__order', 'granted_in__order__event'
        )
        ctx['invoice_addresses'] = InvoiceAddress.profiles.filter(customer=self.request.customer)
        ctx['is_paginated'] = True

        for m in ctx['memberships']:
            if m.membership_type.max_usages:
                m.percent = int(m.usages / m.membership_type.max_usages * 100)
            else:
                m.percent = 0

        s = OrderPosition.objects.filter(
            order=OuterRef('pk')
        ).order_by().values('order').annotate(k=Count('id')).values('k')
        annotated = {
            o['pk']: o
            for o in
            Order.annotate_overpayments(Order.objects, sums=True).filter(
                pk__in=[o.pk for o in ctx['orders']]
            ).annotate(
                pcnt=Subquery(s, output_field=IntegerField()),
            ).values(
                'pk', 'pcnt',
            )
        }

        for o in ctx['orders']:
            if o.pk not in annotated:
                continue
            o.count_positions = annotated.get(o.pk)['pcnt']
        return ctx


class MembershipUsageView(CustomerRequiredMixin, ListView):
    template_name = 'pretixpresale/organizers/customer_membership.html'
    context_object_name = 'usages'
    paginate_by = 20

    @cached_property
    def membership(self):
        return get_object_or_404(
            self.request.customer.memberships,
            pk=self.kwargs.get('id')
        )

    def get_queryset(self):
        return self.membership.orderposition_set.select_related(
            'order', 'order__event', 'subevent', 'item', 'variation',
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['membership'] = self.membership
        ctx['is_paginated'] = True
        return ctx


class AddressDeleteView(CustomerRequiredMixin, CompatDeleteView):
    template_name = 'pretixpresale/organizers/customer_address_delete.html'
    context_object_name = 'address'

    def get_object(self, **kwargs):
        return get_object_or_404(InvoiceAddress.profiles, customer=self.request.customer, pk=self.kwargs.get('id'))

    def get_success_url(self):
        return eventreverse(self.request.organizer, 'presale:organizer.customer.profile', kwargs={})


class ProfileDeleteView(CustomerRequiredMixin, CompatDeleteView):
    template_name = 'pretixpresale/organizers/customer_profile_delete.html'
    context_object_name = 'profile'

    def get_object(self, **kwargs):
        return get_object_or_404(self.request.customer.attendee_profiles, pk=self.kwargs.get('id'))

    def get_success_url(self):
        return eventreverse(self.request.organizer, 'presale:organizer.customer.profile', kwargs={})


class ChangePasswordView(CustomerRequiredMixin, FormView):
    template_name = 'pretixpresale/organizers/customer_password.html'
    form_class = ChangePasswordForm

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts:
            raise Http404('Feature not enabled')
        if self.request.customer and self.request.customer.provider_id:
            raise Http404('Feature not enabled')
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return eventreverse(self.request.organizer, 'presale:organizer.customer.profile', kwargs={})

    @transaction.atomic()
    def form_valid(self, form):
        customer = form.customer
        customer.log_action('pretix.customer.password.set', {})
        customer.set_password(form.cleaned_data['password'])
        customer.save()
        messages.success(self.request, _('Your changes have been saved.'))
        update_customer_session_auth_hash(self.request, customer)
        return HttpResponseRedirect(self.get_success_url())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['customer'] = self.request.customer
        return kwargs


class ChangeInformationView(CustomerRequiredMixin, FormView):
    template_name = 'pretixpresale/organizers/customer_info.html'
    form_class = ChangeInfoForm

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts:
            raise Http404('Feature not enabled')
        if self.request.customer:
            self.initial_email = self.request.customer.email
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return eventreverse(self.request.organizer, 'presale:organizer.customer.profile', kwargs={})

    def form_valid(self, form):
        if form.cleaned_data['email'] != self.initial_email and not self.request.customer.provider:
            new_email = form.cleaned_data['email']
            form.cleaned_data['email'] = form.instance.email = self.initial_email
            ctx = form.instance.get_email_context()
            ctx['url'] = build_absolute_uri(
                self.request.organizer,
                'presale:organizer.customer.change.confirm'
            ) + '?token=' + dumps({
                'customer': form.instance.pk,
                'email': new_email
            }, salt='pretix.presale.views.customer.ChangeInformationView')
            mail(
                new_email,
                self.request.organizer.settings.mail_subject_customer_email_change,
                self.request.organizer.settings.mail_text_customer_email_change,
                ctx,
                locale=form.instance.locale,
                customer=form.instance,
                organizer=self.request.organizer,
            )
            messages.success(self.request, _('Your changes have been saved. We\'ve sent you an email with a link to update your '
                                             'email address. The email address of your account will be changed as soon as you '
                                             'click that link.'))
        else:
            messages.success(self.request, _('Your changes have been saved.'))

        with transaction.atomic():
            form.save()
            d = dict(form.cleaned_data)
            del d['email']
            self.request.customer.log_action('pretix.customer.changed', d)

        update_customer_session_auth_hash(self.request, form.instance)
        return HttpResponseRedirect(self.get_success_url())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        kwargs['instance'] = self.request.customer
        return kwargs


class ConfirmChangeView(View):
    template_name = 'pretixpresale/organizers/customer_info.html'

    def get(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts:
            raise Http404('Feature not enabled')

        try:
            data = loads(request.GET.get('token', ''), salt='pretix.presale.views.customer.ChangeInformationView', max_age=3600 * 24)
        except BadSignature:
            messages.error(request, _('You clicked an invalid link.'))
            return HttpResponseRedirect(self.get_success_url())

        try:
            customer = request.organizer.customers.get(pk=data.get('customer'), provider__isnull=True)
        except Customer.DoesNotExist:
            messages.error(request, _('You clicked an invalid link.'))
            return HttpResponseRedirect(self.get_success_url())

        with transaction.atomic():
            customer.email = data['email']
            customer.save()
            customer.log_action('pretix.customer.changed', {
                'email': data['email']
            })

        messages.success(request, _('Your email address has been updated.'))

        if customer == request.customer:
            update_customer_session_auth_hash(self.request, customer)

        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return eventreverse(self.request.organizer, 'presale:organizer.customer.profile', kwargs={})


class SSOLoginView(RedirectBackMixin, View):
    """
    Start logging in with a SSO provider.
    """
    form_class = AuthenticationForm
    redirect_authenticated_user = True

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts:
            raise Http404('Feature not enabled')
        if self.redirect_authenticated_user and self.request.customer:
            redirect_to = self.get_success_url()
            if redirect_to == self.request.path:
                raise ValueError(
                    "Redirection loop for authenticated user detected. Check that "
                    "your LOGIN_REDIRECT_URL doesn't point to a login page."
                )
            return HttpResponseRedirect(redirect_to)
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def provider(self):
        return get_object_or_404(self.request.organizer.sso_providers.filter(is_active=True), pk=self.kwargs['provider'])

    def get(self, request, *args, **kwargs):
        next_url = request.GET.get('next') or ''
        popup_origin = request.GET.get('popup_origin', '')
        if popup_origin:
            popup_origin_parsed = urlparse(popup_origin)
            untrusted = (
                popup_origin_parsed.hostname != urlparse(settings.SITE_URL).hostname and
                not KnownDomain.objects.filter(domainname=popup_origin_parsed.hostname, organizer=self.request.organizer.pk).exists()
            )
            if untrusted:
                # Do not accept faked origins
                popup_origin = None

        nonce = get_random_string(32)
        request.session[f'pretix_customerauth_{self.provider.pk}_nonce'] = nonce
        request.session[f'pretix_customerauth_{self.provider.pk}_popup_origin'] = popup_origin
        request.session[f'pretix_customerauth_{self.provider.pk}_cross_domain_requested'] = self.request.GET.get("request_cross_domain_customer_auth") == "true"
        redirect_uri = build_absolute_uri(self.request.organizer, 'presale:organizer.customer.login.return', kwargs={
            'provider': self.provider.pk
        })

        if self.provider.method == "oidc":
            return redirect_to_url(oidc_authorize_url(self.provider, f'{nonce}%{next_url}', redirect_uri))
        else:
            raise Http404("Unknown SSO method.")

    def get_success_url(self):
        url = self.get_redirect_url()

        if not url:
            return eventreverse(self.request.organizer, 'presale:organizer.customer.profile', kwargs={})
        return url


class SSOLoginReturnView(RedirectBackMixin, View):
    """
    Start logging in with a SSO provider.
    """
    form_class = AuthenticationForm
    redirect_authenticated_user = True

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        if not request.organizer.settings.customer_accounts:
            raise Http404('Feature not enabled')
        if self.redirect_authenticated_user and self.request.customer:
            redirect_to = self.get_success_url()
            if redirect_to == self.request.path:
                raise ValueError(
                    "Redirection loop for authenticated user detected. Check that "
                    "your LOGIN_REDIRECT_URL doesn't point to a login page."
                )
            return HttpResponseRedirect(redirect_to)
        r = super().dispatch(request, *args, **kwargs)
        request.session.pop(f'pretix_customerauth_{self.provider.pk}_nonce', None)
        request.session.pop(f'pretix_customerauth_{self.provider.pk}_popup_origin', None)
        request.session.pop(f'pretix_customerauth_{self.provider.pk}_cross_domain_requested', None)
        return r

    @cached_property
    def provider(self):
        return get_object_or_404(self.request.organizer.sso_providers.filter(is_active=True), pk=self.kwargs['provider'])

    def get(self, request, *args, **kwargs):
        redirect_to = None
        popup_origin = None

        if request.session.get(f'pretix_customerauth_{self.provider.pk}_popup_origin'):
            popup_origin = request.session[f'pretix_customerauth_{self.provider.pk}_popup_origin']

        if self.provider.method == "oidc":
            if not request.GET.get('state'):
                return self._fail(
                    _('Login was not successful. Error message: "{error}".').format(
                        error='state parameter missing',
                    ),
                    popup_origin,
                )

            nonce, redirect_to = re.split("[%#§]", request.GET['state'], 1)  # Allow § and # for backwards-compatibility for a while

            if nonce != request.session.get(f'pretix_customerauth_{self.provider.pk}_nonce'):
                return self._fail(
                    _('Login was not successful. Error message: "{error}".').format(
                        error='invalid one-time token',
                    ),
                    popup_origin,
                )
            redirect_uri = build_absolute_uri(
                self.request.organizer, 'presale:organizer.customer.login.return',
                kwargs={
                    'provider': self.provider.pk
                }
            )
            try:
                profile = oidc_validate_authorization(
                    self.provider,
                    request.GET.get('code'),
                    redirect_uri,
                )
            except ValidationError as e:
                for msg in e:
                    return self._fail(msg, popup_origin)
        else:
            raise Http404("Unknown SSO method.")

        identifier = hashlib.sha256(
            profile['uid'].encode() + b'@' + str(self.provider.pk).encode()
        ).hexdigest().upper()[:settings.ENTROPY['customer_identifier']]
        if "1" not in identifier and "0" not in identifier:
            # This is a hack to make sure the hash space does not overlap with the random identifiers generated by
            # Customer.assign_identifier()
            identifier = identifier[:4] + "1" + identifier[4:-1]

        try:
            customer = self.request.organizer.customers.get(
                provider=self.provider,
                identifier=identifier,
            )
        except Customer.MultipleObjectsReturned:
            return self._fail(
                _('Login was not successful. Error message: "{error}".').format(
                    error='identifier not unique',
                ),
                popup_origin,
            )
        except Customer.DoesNotExist:
            name_scheme = self.request.organizer.settings.name_scheme
            name_parts = {
                '_scheme': name_scheme,
            }
            scheme = PERSON_NAME_SCHEMES.get(name_scheme)
            for fname, label, size in scheme['fields']:
                if fname in profile:
                    name_parts[fname] = profile[fname] or ''
            if len(name_parts) == 1 and profile.get('name'):
                name_parts = {'_legacy': profile['name']}
            customer = Customer(
                organizer=self.request.organizer,
                identifier=identifier,
                external_identifier=profile['uid'],
                provider=self.provider,
                email=profile['email'],
                phone=profile.get('phone') or None,
                name_parts=name_parts,
                is_active=True,
                is_verified=True,  # todo: always?
                locale=request.LANGUAGE_CODE,
            )
            try:
                customer.save(force_insert=True)
                customer_created.send(customer.organizer, customer=customer)
            except IntegrityError:
                # This might either be a race condition or the email address is taken
                # by a different customer account
                try:
                    customer = self.request.organizer.customers.get(
                        provider=self.provider,
                        identifier=identifier,
                    )
                except Customer.DoesNotExist:
                    return self._fail(
                        _('We were unable to use your login since the email address {email} is already used for a '
                          'different account in this system.').format(email=profile['email']),
                        popup_origin,
                    )
        else:
            if customer.is_active and customer.email != profile['email']:
                customer.email = profile['email']
                try:
                    customer.save(update_fields=['email'])
                except IntegrityError:
                    return self._fail(
                        _('We were unable to use your login since the email address {email} is already used for a '
                          'different account in this system.').format(email=profile['email']),
                        popup_origin,
                    )
                customer.log_action('pretix.customer.changed', {
                    'email': profile['email'],
                    '_source': 'provider'
                })

        if customer.external_identifier != profile['uid']:
            return self._fail(
                _('Login was not successful. Error message: "{error}".').format(
                    error='identifier not unique',
                ),
                popup_origin,
            )

        if not customer.is_active:
            self._fail(
                AuthenticationForm.error_messages['inactive'],
                popup_origin,
            )

        if not customer.is_verified:
            return self._fail(
                AuthenticationForm.error_messages['unverified'],
                popup_origin
            )

        if popup_origin:
            return render(self.request, 'pretixpresale/postmessage.html', {
                'message': {
                    '__process': 'customer_sso_popup',
                    'status': 'ok',
                    'value': dumps({
                        'customer': customer.pk,
                    }, salt=f'customer_sso_popup_{self.request.organizer.pk}')
                },
                'origin': popup_origin,
            })
        else:
            customer_login(self.request, customer)
            customer_signed_in.send(customer.organizer, customer=customer)
            return redirect_to_url(self.get_success_url(redirect_to))

    def _fail(self, message, popup_origin):
        if not popup_origin:
            messages.error(
                self.request,
                message,
            )
            return redirect(eventreverse(self.request.organizer, 'presale:organizer.customer.login', kwargs={}))
        else:
            return render(self.request, 'pretixpresale/postmessage.html', {
                'message': {
                    '__process': 'customer_sso_popup',
                    'status': 'error',
                    'value': str(message)
                },
                'origin': popup_origin,
            })

    def get_success_url(self, redirect_to=None):
        url = self.get_redirect_url(redirect_to)

        if not url:
            return eventreverse(self.request.organizer, 'presale:organizer.customer.profile', kwargs={})
        else:
            if self.request.session.get(f'pretix_customerauth_{self.provider.pk}_cross_domain_requested'):
                otpstore = SessionStore()
                otpstore[f'customer_cross_domain_auth_{self.request.organizer.pk}'] = self.request.session.session_key
                otpstore.set_expiry(60)
                otpstore.save(must_create=True)
                otp = otpstore.session_key

                u = urlparse(url)
                qsl = parse_qs(u.query)
                qsl['cross_domain_customer_auth'] = otp
                url = urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(qsl, doseq=True), u.fragment))

        return url
