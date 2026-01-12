from django.urls import reverse
from django.views.generic import ListView
from pretix.base.models import Event, LogEntry
from pretix.control.views.event import EventSettingsFormView, EventPermissionRequiredMixin
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

class MisaHistoryView(EventPermissionRequiredMixin, ListView):
    model = LogEntry
    template_name = 'pretixplugins/misa/history.html'
    permission = 'can_view_orders'
    context_object_name = 'logs'
    paginate_by = 20

    def get_queryset(self):
        return LogEntry.objects.filter(
            event=self.request.event,
            action_type__startswith='pretix.plugins.misa'
        ).select_related('order').order_by('-datetime')
