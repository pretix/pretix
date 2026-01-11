from django import forms
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.forms import SettingsForm
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsView, EventSettingsFormView

class ZaloZNSSettingsForm(SettingsForm):
    zalozns_enabled = forms.BooleanField(
        label=_('Enable Zalo ZNS'),
        required=False,
    )
    zalozns_access_token = forms.CharField(
        label=_('Access Token'),
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
    )
    zalozns_template_id = forms.CharField(
        label=_('Template ID'),
        required=False,
    )
    zalozns_template_data_mapping = forms.CharField(
        label=_('Template Data Mapping (JSON)'),
        required=False,
        widget=forms.Textarea,
        help_text=_('JSON mapping order fields to ZNS template parameters. E.g. {"customer_name": "name", "order_code": "code"}'),
        initial='{"customer_name": "name", "order_code": "code"}'
    )

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
