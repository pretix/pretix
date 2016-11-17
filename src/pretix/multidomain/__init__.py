from django.apps import AppConfig


class PretixMultidomainConfig(AppConfig):
    name = 'pretix.multidomain'
    label = 'pretixmultidomain'


default_app_config = 'pretix.multidomain.PretixMultidomainConfig'
