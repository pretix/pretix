from django import forms
from django.utils.translation import gettext_lazy as _
from pretix.base.forms import SettingsForm

class MisaSettingsForm(SettingsForm):
    misa_enabled = forms.BooleanField(
        label=_('Enable MISA E-Invoice'),
        required=False,
    )
    misa_url = forms.URLField(
        label=_('API URL'),
        required=False,
        initial='https://einvoice-api.misa.vn',
        help_text=_('The base URL of MISA E-Invoice API'),
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
        widget=forms.PasswordInput(render_value=True),
    )
    misa_template_code = forms.CharField(
        label=_('Template Code'),
        required=False,
        help_text=_('E.g. 1/001')
    )
    misa_series = forms.CharField(
        label=_('Invoice Series (Ký hiệu)'),
        required=False,
        help_text=_('E.g. C23TAA')
    )
