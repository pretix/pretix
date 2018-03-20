from django.apps import AppConfig


class PretixHelpersConfig(AppConfig):
    name = 'pretix.helpers'
    label = 'pretixhelpers'


default_app_config = 'pretix.helpers.PretixHelpersConfig'
