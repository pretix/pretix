from django.apps import AppConfig


class PretixApiConfig(AppConfig):
    name = 'pretix.api'
    label = 'pretixapi'

    def ready(self):
        from . import signals, webhooks  # noqa


default_app_config = 'pretix.api.PretixApiConfig'
