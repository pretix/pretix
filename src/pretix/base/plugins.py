import sys
from enum import Enum
from typing import List

from django.apps import AppConfig, apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class PluginType(Enum):
    """
    Plugin type classification. THIS IS DEPRECATED, DO NOT USE ANY MORE.
    This is only not removed yet as external plugins might have references
    to this enum.
    """
    RESTRICTION = 1
    PAYMENT = 2
    ADMINFEATURE = 3
    EXPORT = 4


def get_all_plugins(event=None) -> List[type]:
    """
    Returns the PretixPluginMeta classes of all plugins found in the installed Django apps.
    """
    plugins = []
    for app in apps.get_app_configs():
        if hasattr(app, 'PretixPluginMeta'):
            meta = app.PretixPluginMeta
            meta.module = app.name
            meta.app = app
            if app.name in settings.PRETIX_PLUGINS_EXCLUDE:
                continue

            if hasattr(app, 'is_available') and event:
                if not app.is_available(event):
                    continue

            plugins.append(meta)
    return sorted(
        plugins,
        key=lambda m: (0 if m.module.startswith('pretix.') else 1, str(m.name).lower().replace('pretix ', ''))
    )


class PluginConfig(AppConfig):
    IGNORE = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'PretixPluginMeta'):
            raise ImproperlyConfigured("A pretix plugin config should have a PretixPluginMeta inner class.")

        if hasattr(self.PretixPluginMeta, 'compatibility') and not self.IGNORE:
            import pkg_resources
            try:
                pkg_resources.require(self.PretixPluginMeta.compatibility)
            except pkg_resources.VersionConflict as e:
                print("Incompatible plugins found!")
                print("Plugin {} requires you to have {}, but you installed {}.".format(
                    self.name, e.req, e.dist
                ))
                sys.exit(1)
