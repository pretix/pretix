from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")


class PluginApp(PluginConfig):
    default = True
    name = "pretix_sideburn_lottery"
    verbose_name = "Sideburn Lottery"

    class PretixPluginMeta:
        name = gettext_lazy("Sideburn Lottery")
        author = "Ryan"
        description = gettext_lazy(
            "Waiting-list lottery mechanics for Sideburn events"
        )
        visible = True
        version = __version__
        category = "FEATURE"
        compatibility = "pretix>=2.7.0"
        settings_links = []
        navigation_links = []

    def ready(self):
        from . import signals  # NOQA
