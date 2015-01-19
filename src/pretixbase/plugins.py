try:  # NOQA
    from enum import Enum
except ImportError:  # NOQA
    from flufl.enum import Enum  # remove this dependency when support for python <=3.3 is dropped

from django.apps import apps


class PluginType(Enum):
    RESTRICTION = 1


def get_all_plugins() -> "List[class]":
    """
    Returns the TixlPluginMeta classes of all plugins found in the installed Django apps.
    """
    plugins = []
    for app in apps.get_app_configs():
        if hasattr(app, 'TixlPluginMeta'):
            meta = app.TixlPluginMeta
            meta.module = app.name
            plugins.append(meta)
    return plugins
