from django.apps import AppConfig


class PretixBaseConfig(AppConfig):
    name = 'pretix.base'
    label = 'pretixbase'

default_app_config = 'pretix.base.PretixBaseConfig'
