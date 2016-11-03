from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _

from pretix import __version__ as version


class StatisticsApp(AppConfig):
    name = 'pretix.plugins.statistics'
    verbose_name = _("Statistics")

    class PretixPluginMeta:
        name = _("Statistics")
        author = _("the pretix team")
        version = version
        description = _("This plugin shows you various statistics.")

    def ready(self):
        from . import signals  # NOQA


default_app_config = 'pretix.plugins.statistics.StatisticsApp'
