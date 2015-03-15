from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _
from pretix.base.plugins import PluginType


class PaypalApp(AppConfig):
    name = 'pretix.plugins.paypal'
    verbose_name = _("Stripe")

    class PretixPluginMeta:
        type = PluginType.PAYMENT
        name = _("PayPal")
        author = _("the pretix team")
        version = '1.0.0'
        description = _("This plugin allows you to receive payments via PayPal")

    def ready(self):
        from . import signals  # NOQA


default_app_config = 'pretix.plugins.paypal.PaypalApp'
