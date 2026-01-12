from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _
from . import __version__


class OnePayApp(AppConfig):
    name = 'pretix.plugins.onepay'
    verbose_name = _("OnePay")

    class PretixPluginMeta:
        name = _("OnePay")
        author = "Pretix Integration"
        description = _("Integration for OnePay payment gateway")
        visible = True
        version = __version__
        category = 'PAYMENT'

    def ready(self):
        from . import signals  # NOQA
