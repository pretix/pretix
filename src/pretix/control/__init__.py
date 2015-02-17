from django.apps import AppConfig


class PretixControlConfig(AppConfig):
    name = 'pretix.control'
    label = 'pretixcontrol'

default_app_config = 'pretix.control.PretixControlConfig'
