from django.apps import AppConfig
from tixlbase.plugins import PluginType


class TestDummyApp(AppConfig):
    name = 'tixlplugins.testdummy'
    verbose_name = '.testdummy'

    class TixlPluginMeta:
        type = PluginType.RESTRICTION
        name = '.testdummy'
        version = '1.0.0'

    def ready(self):
        from . import signals  # NOQA

default_app_config = 'tixlplugins.testdummy.TestDummyApp'
