import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import ListView, TemplateView
from hijack.helpers import login_user, release_hijack

from pretix.base.auth import get_auth_backends
from pretix.base.models import User
from pretix.base.services.mail import SendMailException
from pretix.control.forms.filter import UserFilterForm
from pretix.control.forms.users import UserEditForm
from pretix.control.permissions import AdministratorPermissionRequiredMixin
from pretix.control.views import CreateView, UpdateView
from pretix.control.views.user import RecentAuthenticationRequiredMixin


class UserListView(AdministratorPermissionRequiredMixin, ListView):
    template_name = 'pretixcontrol/users/index.html'
    context_object_name = 'users'
    paginate_by = 30

    def get_queryset(self):
        qs = User.objects.all()
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

    @cached_property
    def filter_form(self):
        return UserFilterForm(data=self.request.GET)


class UserEditView(AdministratorPermissionRequiredMixin, RecentAuthenticationRequiredMixin, UpdateView):
    template_name = 'pretixcontrol/users/form.html'
    context_object_name = 'user'
    form_class = UserEditForm

    def get_object(self, queryset=None):
        return get_object_or_404(User, pk=self.kwargs.get("id"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['teams'] = self.object.teams.select_related('organizer')
        b = get_auth_backends()
        ctx['backend'] = (
            b[self.object.auth_backend].verbose_name if self.object.auth_backend in b else self.object.auth_backend
        )
        return ctx

    def get_success_url(self):
        return reverse('control:users.edit', kwargs=self.kwargs)

    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))

        data = {}
        for k in form.changed_data:
            if k != 'new_pw_repeat':
                if 'new_pw' == k:
                    data['new_pw'] = True
                else:
                    data[k] = form.cleaned_data[k]

        sup = super().form_valid(form)

        if 'require_2fa' in form.changed_data and form.cleaned_data['require_2fa']:
            self.object.log_action('pretix.user.settings.2fa.enabled', user=self.request.user)
        elif 'require_2fa' in form.changed_data and not form.cleaned_data['require_2fa']:
            self.object.log_action('pretix.user.settings.2fa.disabled', user=self.request.user)
        self.object.log_action('pretix.user.settings.changed', user=self.request.user, data=data)

        return sup


class UserResetView(AdministratorPermissionRequiredMixin, RecentAuthenticationRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        return redirect(reverse('control:users.edit', kwargs=self.kwargs))

    def post(self, request, *args, **kwargs):
        self.object = get_object_or_404(User, pk=self.kwargs.get("id"))
        try:
            self.object.send_password_reset()
        except SendMailException:
            messages.error(request, _('There was an error sending the mail. Please try again later.'))
            return redirect(self.get_success_url())

        self.object.log_action('pretix.control.auth.user.forgot_password.mail_sent',
                               user=request.user)
        messages.success(request, _('We sent out an e-mail containing further instructions.'))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('control:users.edit', kwargs=self.kwargs)


class UserAnonymizeView(AdministratorPermissionRequiredMixin, RecentAuthenticationRequiredMixin, TemplateView):
    template_name = "pretixcontrol/users/anonymize.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['user'] = get_object_or_404(User, pk=self.kwargs.get("id"))
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = get_object_or_404(User, pk=self.kwargs.get("id"))
        self.object.log_action('pretix.user.anonymized',
                               user=request.user)
        self.object.email = "{}@disabled.pretix.eu".format(self.object.pk)
        self.object.fullname = ""
        self.object.is_active = False
        self.object.notifications_send = False
        self.object.save()
        for le in self.object.all_logentries.filter(action_type="pretix.user.settings.changed"):
            d = le.parsed_data
            if 'email' in d:
                d['email'] = '█'
            if 'fullname' in d:
                d['fullname'] = '█'
            le.data = json.dumps(d)
            le.shredded = True
            le.save(update_fields=['data', 'shredded'])

        return redirect(reverse('control:users.edit', kwargs=self.kwargs))


class UserImpersonateView(AdministratorPermissionRequiredMixin, RecentAuthenticationRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        return redirect(reverse('control:users.edit', kwargs=self.kwargs))

    def post(self, request, *args, **kwargs):
        self.object = get_object_or_404(User, pk=self.kwargs.get("id"))
        self.request.user.log_action('pretix.control.auth.user.impersonated',
                                     user=request.user,
                                     data={
                                         'other': self.kwargs.get("id"),
                                         'other_email': self.object.email
                                     })
        oldkey = request.session.session_key
        login_user(request, self.object)
        request.session['hijacker_session'] = oldkey
        return redirect(reverse('control:index'))


class UserImpersonateStopView(LoginRequiredMixin, View):

    def post(self, request, *args, **kwargs):
        impersonated = request.user
        hijs = request.session['hijacker_session']
        release_hijack(request)
        ss = request.user.get_active_staff_session(hijs)
        if ss:
            request.session.save()
            ss.session_key = request.session.session_key
            ss.save()

        request.user.log_action('pretix.control.auth.user.impersonate_stopped',
                                user=request.user,
                                data={
                                    'other': impersonated.pk,
                                    'other_email': impersonated.email
                                })
        return redirect(reverse('control:index'))


class UserCreateView(AdministratorPermissionRequiredMixin, RecentAuthenticationRequiredMixin, CreateView):
    template_name = 'pretixcontrol/users/create.html'
    context_object_name = 'user'
    form_class = UserEditForm

    def get_form(self, form_class=None):
        f = super().get_form(form_class)
        f.fields['new_pw'].required = True
        f.fields['new_pw_repeat'].required = True
        return f

    def get_initial(self):
        i = super().get_initial()
        i['timezone'] = settings.TIME_ZONE
        return i

    def get_success_url(self):
        return reverse('control:users')

    def form_valid(self, form):
        messages.success(self.request, _('The new user has been created.'))
        return super().form_valid(form)
