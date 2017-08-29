from django.apps import AppConfig
from django.urls import RegexURLPattern


class PretixMultidomainConfig(AppConfig):
    name = 'pretix.multidomain'
    label = 'pretixmultidomain'


default_app_config = 'pretix.multidomain.PretixMultidomainConfig'


def event_url(regex, view, kwargs=None, name=None, require_live=True):
    if callable(view):
        r = RegexURLPattern(regex, view, kwargs, name)
        r._require_live = require_live
        return r
    else:
        raise TypeError('view must be a callable.')
