from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _

from pretix.base.plugins import PluginType


class StatisticsApp(AppConfig):
    name = 'pretix.plugins.statistics'
    verbose_name = _("Statistics")

    class PretixPluginMeta:
        type = PluginType.ADMINFEATURE
        name = _("Statistics")
        author = _("the pretix team")
        version = '1.0.0'
        description = _("This plugin shows you various statistics.")

    def ready(self):
        from . import signals  # NOQA


default_app_config = 'pretix.plugins.statistics.StatisticsApp'
