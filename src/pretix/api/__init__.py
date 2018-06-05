from django.apps import AppConfig


class PretixApiConfig(AppConfig):
    name = 'pretix.api'
    label = 'pretixapi'


default_app_config = 'pretix.api.PretixApiConfig'
