from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.core.urlresolvers import reverse
from django.views.generic import UpdateView
from django.utils.translation import ugettext_lazy as _
from pretix.control.forms.user import UserSettingsForm

from pretix.base.models import User


class UserSettings(UpdateView):
    model = User
    form_class = UserSettingsForm
    template_name = 'pretixcontrol/user/settings.html'

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
        return reverse('control:user.settings')
