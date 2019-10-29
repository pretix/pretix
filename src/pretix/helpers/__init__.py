from django.apps import AppConfig

from .database import *  # noqa


class PretixHelpersConfig(AppConfig):
    name = 'pretix.helpers'
    label = 'pretixhelpers'


default_app_config = 'pretix.helpers.PretixHelpersConfig'
