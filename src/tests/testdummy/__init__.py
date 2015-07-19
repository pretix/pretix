from django.apps import AppConfig

from pretix.base.plugins import PluginType


class TestDummyApp(AppConfig):
    name = 'tests.testdummy'
    verbose_name = '.testdummy'

    class PretixPluginMeta:
        type = PluginType.RESTRICTION
        name = '.testdummy'
        version = '1.0.0'

    def ready(self):
        from tests.testdummy import signals  # noqa


default_app_config = 'tests.testdummy.TestDummyApp'
