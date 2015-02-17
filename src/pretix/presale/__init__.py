from django.apps import AppConfig


class PretixPresaleConfig(AppConfig):
    name = 'pretix.presale'
    label = 'pretixpresale'

default_app_config = 'pretix.presale.PretixPresaleConfig'
