from collections import OrderedDict

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
        for r, response in responses:
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value
