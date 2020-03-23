from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

from pretix import __version__ as version


class ReturnURLApp(AppConfig):
    name = 'pretix.plugins.returnurl'
    verbose_name = _("Redirection from order page")

    class PretixPluginMeta:
        name = _("Redirection from order page")
        author = _("the pretix team")
        version = version
        category = 'API'
        description = _("This plugin allows to link to payments and redirect back afterwards. This is useful in "
                        "combination with our API.")

    def ready(self):
        from . import signals  # NOQA


default_app_config = 'pretix.plugins.returnurl.ReturnURLApp'
