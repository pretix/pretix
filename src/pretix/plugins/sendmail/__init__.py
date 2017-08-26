from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _

from pretix import __version__ as version


class SendMailApp(AppConfig):
    name = 'pretix.plugins.sendmail'
    verbose_name = _("Send out emails")

    class PretixPluginMeta:
        name = _("Send out emails")
        author = _("the pretix team")
        version = version
        description = _("This plugin allows you to send out emails " +
                        "to all your customers.")

    def ready(self):
        from . import signals  # NOQA


default_app_config = 'pretix.plugins.sendmail.SendMailApp'
