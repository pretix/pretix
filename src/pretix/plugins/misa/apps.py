from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _
from . import __version__

class MisaApp(AppConfig):
    name = 'pretix.plugins.misa'
    verbose_name = _("MISA E-Invoice")

    class PretixPluginMeta:
        name = _("MISA E-Invoice")
        author = "Pretix Integration"
        description = _("Generate MISA e-invoices for orders")
        visible = True
        version = __version__
        category = 'INTEGRATION'

    def ready(self):
        from . import signals  # NOQA
