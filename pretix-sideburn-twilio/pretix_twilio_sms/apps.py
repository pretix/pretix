from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")


class PluginApp(PluginConfig):
    default = True
    name = "pretix_twilio_sms"
    verbose_name = "Sideburn Twilio Integration"

    class PretixPluginMeta:
        name = gettext_lazy("Sideburn Twilio Integration")
        author = "Ryan"
        description = gettext_lazy("A Sideburn-specific twilio integration for pretix")
        visible = True
        version = __version__
        category = "INTEGRATION"
        compatibility = "pretix>=2.7.0"
        settings_links = []
        navigation_links = []

    def ready(self):
        from . import signals  # NOQA
        self._patch_customer_views()

    def _patch_customer_views(self):
        from django.apps import apps

        if not apps.is_installed("pretix_twilio_sms"):
            return

        from pretix.presale.views import customer as presale_customer

        def profile_get_template_names(self):
            return ["pretix_twilio_sms/customer_profile.html"]

        presale_customer.ProfileView.get_template_names = profile_get_template_names
