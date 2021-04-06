from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import FormView, View

from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.forms.customer import AuthenticationForm
from pretix.presale.utils import customer_login, customer_logout


class LoginView(FormView):
    """
    Display the login form and handle the login action.
    """
    form_class = AuthenticationForm
    redirect_field_name = 'next'
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

    def get_success_url(self):
        url = self.get_redirect_url()
        return url or eventreverse(self.request.organizer, 'presale:organizer.customer.profile', kwargs={})

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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        """Security check complete. Log the user in."""
        customer_login(self.request, form.get_customer())
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'next': self.get_redirect_url(),
            **(self.extra_context or {})
        })
        return context


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
