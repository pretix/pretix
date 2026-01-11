from django import forms
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.forms import SettingsForm
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsView, EventSettingsFormView

class MisaSettingsForm(SettingsForm):
    misa_enabled = forms.BooleanField(
        label=_('Enable MISA E-Invoice'),
        required=False,
    )
    misa_url = forms.URLField(
        label=_('API URL'),
        required=False,
        initial='https://einvoice-api.misa.vn',
    )
    misa_app_id = forms.CharField(
        label=_('App ID'),
        required=False,
    )
    misa_tax_code = forms.CharField(
        label=_('Tax Code'),
        required=False,
    )
    misa_username = forms.CharField(
        label=_('Username'),
        required=False,
    )
    misa_password = forms.CharField(
        label=_('Password'),
        required=False,
        widget=forms.PasswordInput,
    )
    misa_template_code = forms.CharField(
        label=_('Template Code'),
        required=False,
    )
    misa_series = forms.CharField(
        label=_('Invoice Series (Ký hiệu)'),
        required=False,
    )

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
