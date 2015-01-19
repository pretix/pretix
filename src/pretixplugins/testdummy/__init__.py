from django.apps import AppConfig
from pretixbase.plugins import PluginType


class TestDummyApp(AppConfig):
    name = 'pretixplugins.testdummy'
    verbose_name = '.testdummy'

    class TixlPluginMeta:
        type = PluginType.RESTRICTION
        name = '.testdummy'
        version = '1.0.0'

    def ready(self):
        from . import signals  # NOQA

default_app_config = 'pretixplugins.testdummy.TestDummyApp'
