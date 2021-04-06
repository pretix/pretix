from urllib.parse import quote

from django.contrib import messages
from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import FormView, ListView, View

from pretix.base.models import Customer, Order, OrderPosition
from pretix.base.services.mail import mail
from pretix.multidomain.urlreverse import build_absolute_uri, eventreverse
from pretix.presale.forms.customer import (
    AuthenticationForm, RegistrationForm, ResetPasswordForm, SetPasswordForm,
    TokenGenerator,
)
from pretix.presale.utils import customer_login, customer_logout


class RedirectBackMixin:
    redirect_field_name = 'next'

    def get_redirect_url(self):
        """Return the user-originating redirect URL if it's safe."""
        redirect_to = self.request.POST.get(
            self.redirect_field_name,
            self.request.GET.get(self.redirect_field_name, '')
        )
        url_is_safe = url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts=None,
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
        return kwargs

    def get_success_url(self):
        url = self.get_redirect_url()
        return url or eventreverse(self.request.organizer, 'presale:organizer.customer.profile', kwargs={})

    def form_valid(self, form):
        """Security check complete. Log the user in."""
        customer_login(self.request, form.get_customer())
        return HttpResponseRedirect(self.get_success_url())


class LogoutView(View):
    redirect_field_name = 'next'

    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        customer_logout(request)
        next_page = self.get_next_page()
        return HttpResponseRedirect(next_page)

    def get_next_page(self):
        next_page = eventreverse(self.request.organizer, 'presale:organizer.index', kwargs={})

        if (self.redirect_field_name in self.request.POST or
                self.redirect_field_name in self.request.GET):
            next_page = self.request.POST.get(
                self.redirect_field_name,
                self.request.GET.get(self.redirect_field_name)
            )
            url_is_safe = url_has_allowed_host_and_scheme(
                url=next_page,
                allowed_hosts=None,
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
        return kwargs

    def get_success_url(self):
        url = self.get_redirect_url()
        return url or eventreverse(self.request.organizer, 'presale:organizer.customer.login', kwargs={})

    def form_valid(self, form):
        form.create()
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
        try:
            self.customer = request.organizer.customers.get(identifier=self.request.GET.get('id'))
        except Customer.DoesNotExist:
            messages.error(request, _('You clicked an invalid link.'))
            return HttpResponseRedirect(self.get_success_url())
        if not TokenGenerator().check_token(self.customer, self.request.GET.get('token')):
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
            _('Set a new password for your account at {organizer}').format(organizer=self.request.organizer.name),
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
        if not getattr(request, 'customer', None):
            return redirect(
                eventreverse(self.request.organizer, 'presale:organizer.customer.login', kwargs={}) +
                '?next=' + quote(self.request.path_info + '?' + self.request.GET.urlencode())
            )
        return super().dispatch(request, *args, **kwargs)


class ProfileView(CustomerRequiredMixin, ListView):
    template_name = 'pretixpresale/organizers/customer_profile.html'
    context_object_name = 'orders'
    paginate_by = 50

    def get_queryset(self):
        return self.request.customer.orders.select_related('event').order_by('-datetime')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['customer'] = self.request.customer

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
