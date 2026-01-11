from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _
from . import __version__

class ZaloZNSApp(AppConfig):
    name = 'pretix.plugins.zalozns'
    verbose_name = _("Zalo ZNS Notification")

    class PretixPluginMeta:
        name = _("Zalo ZNS")
        author = "Pretix Integration"
        description = _("Send Zalo ZNS notifications on order confirmation")
        visible = True
        version = __version__
        category = 'INTEGRATION'

    def ready(self):
        from . import signals  # NOQA
