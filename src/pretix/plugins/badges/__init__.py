from django.apps import AppConfig
from django.utils.translation import ugettext, ugettext_lazy as _

from pretix import __version__ as version


class BadgesApp(AppConfig):
    name = 'pretix.plugins.badges'
    verbose_name = _("Badges")

    class PretixPluginMeta:
        name = _("Badges")
        author = _("the pretix team")
        version = version
        description = _("This plugin allows you to generate badges or name tags for your attendees.")

    def ready(self):
        from . import signals  # NOQA

    def installed(self, event):
        if not event.badge_layouts.exists():
            event.badge_layouts.create(
                name=ugettext('Default'),
                default=True,
            )


default_app_config = 'pretix.plugins.badges.BadgesApp'
