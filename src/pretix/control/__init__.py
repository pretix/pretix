from django.apps import AppConfig


class PretixControlConfig(AppConfig):
    name = 'pretix.control'
    label = 'pretixcontrol'

    def ready(self):
        from .views import event_dashboard  # noqa

default_app_config = 'pretix.control.PretixControlConfig'
