from django.shortcuts import reverse
from django.views.generic import FormView

from pretix.control.forms.global_settings import GlobalSettingsForm
from pretix.control.permissions import AdministratorPermissionRequiredMixin


class GlobalSettingsView(AdministratorPermissionRequiredMixin, FormView):
    template_name = 'pretixcontrol/global_settings.html'
    form_class = GlobalSettingsForm

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('control:global-settings')
