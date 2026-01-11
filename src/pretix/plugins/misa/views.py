from django.urls import reverse
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsFormView
from .forms import MisaSettingsForm

class MisaSettings(EventSettingsFormView):
    model = Event
    form_class = MisaSettingsForm
    template_name = 'pretixplugins/misa/settings.html'
    permission = 'can_change_event_settings'

    def get_success_url(self, **kwargs):
        return reverse('plugins:misa:settings', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })
