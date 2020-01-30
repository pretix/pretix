from django.apps import AppConfig
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretix import __version__ as version


class CheckinlistsApp(AppConfig):
    name = 'pretix.plugins.checkinlists'
    verbose_name = _("Check-in lists")

    class PretixPluginMeta:
        name = _("Check-in list exporter")
        author = _("the pretix team")
        version = version
        visible = False
        description = _("This plugin allows you to generate check-in lists for your conference.")

    def ready(self):
        from . import signals  # NOQA

    @cached_property
    def compatibility_errors(self):
        errs = []
        try:
            import reportlab  # NOQA
        except ImportError:
            errs.append("Python package 'reportlab' is not installed.")
        return errs


default_app_config = 'pretix.plugins.checkinlists.CheckinlistsApp'
