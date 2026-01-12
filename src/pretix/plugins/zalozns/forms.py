import json
from django import forms
from django.utils.translation import gettext_lazy as _
from pretix.base.forms import SettingsForm

class ZaloZNSSettingsForm(SettingsForm):
    zalozns_enabled = forms.BooleanField(
        label=_('Enable Zalo ZNS'),
        required=False,
    )
    zalozns_app_id = forms.CharField(
        label=_('Zalo App ID'),
        required=False,
    )
    zalozns_access_token = forms.CharField(
        label=_('Access Token'),
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        help_text=_('Zalo OA Access Token'),
    )
    zalozns_template_id = forms.CharField(
        label=_('Template ID'),
        required=False,
    )
    zalozns_template_data_mapping = forms.CharField(
        label=_('Template Data Mapping (JSON)'),
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
        help_text=_('JSON mapping order fields to ZNS template parameters. Keys are ZNS params, values are pretix fields. Supported: code, total, name, email.'),
        initial='{"customer_name": "name", "order_code": "code"}'
    )

    def clean_zalozns_template_data_mapping(self):
        data = self.cleaned_data.get('zalozns_template_data_mapping')
        if data:
            try:
                json.loads(data)
            except ValueError:
                raise forms.ValidationError(_('Invalid JSON format.'))
        return data
