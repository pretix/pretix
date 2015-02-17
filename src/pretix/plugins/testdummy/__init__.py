from django.apps import AppConfig
from pretix.base.plugins import PluginType


class TestDummyApp(AppConfig):
    name = 'pretix.plugins.testdummy'
    verbose_name = '.testdummy'

    class PretixPluginMeta:
        type = PluginType.RESTRICTION
        name = '.testdummy'
        version = '1.0.0'

    def ready(self):
        from . import signals  # NOQA

default_app_config = 'pretix.plugins.testdummy.TestDummyApp'
