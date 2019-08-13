from django import forms
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import SettingsForm
from pretix.base.models import Event
from pretix.control.views.event import (
    EventSettingsFormView, EventSettingsViewMixin,
)


class ReturnSettingsForm(SettingsForm):
    returnurl_prefix = forms.URLField(
        label=_("Base redirection URL"),
        help_text=_("Redirection will only be allowed to URLs that start with this prefix."),
        required=False,
    )


class ReturnSettings(EventSettingsViewMixin, EventSettingsFormView):
    model = Event
    form_class = ReturnSettingsForm
    template_name = 'returnurl/settings.html'
    permission = 'can_change_settings'

    def get_success_url(self) -> str:
        return reverse('plugins:returnurl:settings', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })
