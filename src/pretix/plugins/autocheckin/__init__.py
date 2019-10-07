from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _

from pretix import __version__ as version


class AutoCheckInApp(AppConfig):
    name = 'pretix.plugins.autocheckin'
    verbose_name = _("Automatic Check-Ins")

    class PretixPluginMeta:
        name = _("Automatic Check-Ins")
        author = _("the pretix team")
        version = version
        visible = False
        description = _("This plugins handles the automatic check-in for specific sales channels.")

    def ready(self):
        from . import signals  # NOQA


default_app_config = 'pretix.plugins.autocheckin.AutoCheckInApp'
