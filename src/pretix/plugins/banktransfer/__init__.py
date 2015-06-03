from django.apps import AppConfig
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from pretix.base.plugins import PluginType


class BankTransferApp(AppConfig):
    name = 'pretix.plugins.banktransfer'
    verbose_name = _("Bank transfer")

    class PretixPluginMeta:
        type = PluginType.PAYMENT
        name = _("Bank transfer")
        author = _("the pretix team")
        version = '1.0.0'
        description = _("This plugin allows you to receive payments " +
                        "via bank transfer ")

    def ready(self):
        from . import signals  # NOQA

    @cached_property
    def compatibility_warnings(self):
        errs = []
        try:
            import chardet  # NOQA
        except ImportError:
            errs.append(_("Install the python package 'chardet' for better CSV import capabilities."))
        return errs


default_app_config = 'pretix.plugins.banktransfer.BankTransferApp'
