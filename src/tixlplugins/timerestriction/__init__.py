from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _
from tixlbase.plugins import PluginType


class TimeRestrictionApp(AppConfig):
    name = 'tixlplugins.timerestriction'
    verbose_name = _("Time restriction")

    class TixlPluginMeta:
        type = PluginType.RESTRICTION
        name = _("Restricition by time")
        author = _("the tixl team")
        version = '1.0.0'
        description = _("This plugin adds the possibility to restrict the sale " +
                        "of a given item or variation to a certain timeframe " +
                        "or change its price during a certain period.")

    def ready(self):
        from . import signals  # NOQA

default_app_config = 'tixlplugins.timerestriction.TimeRestrictionApp'
