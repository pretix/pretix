from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

from pretix import __version__ as version


class WebCheckinApp(AppConfig):
    name = 'pretix.plugins.webcheckin'
    verbose_name = _("Web-based check-in")

    class PretixPluginMeta:
        name = _("Web-based check-in")
        author = _("the pretix team")
        version = version
        category = "FEATURE"
        description = _("This plugin allows you to perform check-in actions in your browser.")

    def ready(self):
        from . import signals  # NOQA


default_app_config = 'pretix.plugins.webcheckin.WebCheckinApp'
