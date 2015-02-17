from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _
from pretix.base.plugins import PluginType


class TimeRestrictionApp(AppConfig):
    name = 'pretix.plugins.timerestriction'
    verbose_name = _("Time restriction")

    class PretixPluginMeta:
        type = PluginType.RESTRICTION
        name = _("Restriction by time")
        author = _("the pretix team")
        version = '1.0.0'
        description = _("This plugin adds the possibility to restrict the sale " +
                        "of a given item or variation to a certain timeframe " +
                        "or change its price during a certain period.")

    def ready(self):
        from . import signals  # NOQA

default_app_config = 'pretix.plugins.timerestriction.TimeRestrictionApp'
