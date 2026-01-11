from django.urls import reverse
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsFormView
from .forms import ZaloZNSSettingsForm

class ZaloZNSSettings(EventSettingsFormView):
    model = Event
    form_class = ZaloZNSSettingsForm
    template_name = 'pretixplugins/zalozns/settings.html'
    permission = 'can_change_event_settings'

    def get_success_url(self, **kwargs):
        return reverse('plugins:zalozns:settings', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })
