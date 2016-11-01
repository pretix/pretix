from django.contrib import messages
from django.shortcuts import reverse
from django.utils.translation import ugettext_lazy as _
from django.views.generic import FormView

from pretix.control.forms.global_settings import GlobalSettingsForm
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
        return reverse('control:global-settings')
