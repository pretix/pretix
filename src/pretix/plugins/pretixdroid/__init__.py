from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _

from pretix import __version__ as version


class PretixdroidApp(AppConfig):
    name = 'pretix.plugins.pretixdroid'
    verbose_name = _("pretixdroid API")

    class PretixPluginMeta:
        name = _("pretixdroid API")
        author = _("the pretix team")
        version = version
        description = _("This plugin allows you to use the pretixdroid Android app for your event.")

    def ready(self):
        from . import signals  # NOQA


default_app_config = 'pretix.plugins.pretixdroid.PretixdroidApp'
