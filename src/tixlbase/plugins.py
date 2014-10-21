try:  # NOQA
    from enum import Enum
except ImportError:  # NOQA
    from flufl.enum import Enum

from django.apps import apps


class PluginType(Enum):
    RESTRICTION = 1


def get_all_plugins() -> "class":
    plugins = []
    for app in apps.get_app_configs():
        if hasattr(app, 'TixlPluginMeta'):
            meta = app.TixlPluginMeta
            meta.module = app.name
            plugins.append(meta)
    return plugins
