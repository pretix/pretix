from enum import Enum
from typing import List

from django.apps import apps
from django.conf import settings


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


def get_all_plugins() -> List[type]:
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
            plugins.append(meta)
    return plugins
