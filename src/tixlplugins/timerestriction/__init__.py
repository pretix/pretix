from django.apps import AppConfig


class TimeRestrictionApp(AppConfig):
    name = 'tixlplugins.timerestriction'
    verbose_name = "Time restriction"

    def ready(self):
        from . import signals

default_app_config = 'tixlplugins.timerestriction.TimeRestrictionApp'
