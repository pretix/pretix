from collections import OrderedDict

from django import forms
from django.utils.translation import ugettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextInput

from pretix.base.forms import SettingsForm
from pretix.base.settings import GlobalSettingsObject
from pretix.base.signals import register_global_settings


class GlobalSettingsForm(SettingsForm):
    def __init__(self, *args, **kwargs):
        self.obj = GlobalSettingsObject()
        super().__init__(*args, obj=self.obj, **kwargs)

        self.fields = OrderedDict([
            ('footer_text', I18nFormField(
                widget=I18nTextInput,
                required=False,
                label=_("Additional footer text"),
                help_text=_("Will be included as additional text in the footer, site-wide.")
            )),
            ('footer_link', I18nFormField(
                widget=I18nTextInput,
                required=False,
                label=_("Additional footer link"),
                help_text=_("Will be included as the link in the additional footer text.")
            ))
        ])
        responses = register_global_settings.send(self)
        for r, response in sorted(responses, key=lambda r: str(r[0])):
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value


class UpdateSettingsForm(SettingsForm):
    update_check_perform = forms.BooleanField(
        required=False,
        label=_("Perform update checks"),
        help_text=_("During the update check, pretix will report an anonymous, unique installation ID, "
                    "the current version of pretix and your installed plugins and the number of active and "
                    "inactive events in your installation to servers operated by the pretix developers. We "
                    "will only store anonymous data, never any IP addresses and we will not know who you are "
                    "or where to find your instance. You can disable this behavior here at any time.")
    )
    update_check_email = forms.EmailField(
        required=False,
        label=_("E-mail notifications"),
        help_text=_("We will notify you at this address if we detect that a new update is available. This "
                    "address will not be transmitted to pretix.eu, the emails will be sent by this server "
                    "locally.")
    )

    def __init__(self, *args, **kwargs):
        self.obj = GlobalSettingsObject()
        super().__init__(*args, obj=self.obj, **kwargs)
