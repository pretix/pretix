from django.contrib import messages
from django.shortcuts import redirect, reverse
from django.utils.translation import ugettext_lazy as _
from django.views.generic import FormView

from pretix.base.services.update_check import check_result_table, update_check
from pretix.base.settings import GlobalSettingsObject
from pretix.control.forms.global_settings import (
    GlobalSettingsForm, UpdateSettingsForm,
)
from pretix.control.permissions import AdministratorPermissionRequiredMixin


class GlobalSettingsView(AdministratorPermissionRequiredMixin, FormView):
    template_name = 'pretixcontrol/global_settings.html'
    form_class = GlobalSettingsForm

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes have not been saved, see below for errors.'))
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse('control:global.settings')


class UpdateCheckView(AdministratorPermissionRequiredMixin, FormView):
    template_name = 'pretixcontrol/global_update.html'
    form_class = UpdateSettingsForm

    def post(self, request, *args, **kwargs):
        if 'trigger' in request.POST:
            update_check.apply()
            return redirect(self.get_success_url())
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes have not been saved, see below for errors.'))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['gs'] = GlobalSettingsObject()
        ctx['gs'].settings.set('update_check_ack', True)
        ctx['tbl'] = check_result_table()
        return ctx

    def get_success_url(self):
        return reverse('control:global.update')
