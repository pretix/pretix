from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

from pretix import __version__ as version


class ManualPaymentApp(AppConfig):
    name = 'pretix.plugins.manualpayment'
    verbose_name = _("Manual payment")

    class PretixPluginMeta:
        name = _("Manual payment")
        author = _("the pretix team")
        version = version
        category = 'PAYMENT'
        description = _("This plugin adds a customizable payment method for manual processing.")


default_app_config = 'pretix.plugins.manualpayment.ManualPaymentApp'
