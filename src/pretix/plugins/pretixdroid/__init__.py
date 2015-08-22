from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _

from pretix.base.plugins import PluginType


class PretixdroidApp(AppConfig):
    name = 'pretix.plugins.pretixdroid'
    verbose_name = _("pretixdroid API")

    class PretixPluginMeta:
        type = PluginType.ADMINFEATURE
        name = _("pretixdroid API")
        author = _("the pretix team")
        version = '1.0.0'
        description = _("This plugin allows you to use the pretixdroid Android app for your event.")

    def ready(self):
        from . import signals  # NOQA


default_app_config = 'pretix.plugins.pretixdroid.PretixdroidApp'
