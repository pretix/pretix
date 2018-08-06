from django.apps import AppConfig
from django.urls import URLPattern
from django.urls.resolvers import RegexPattern


class PretixMultidomainConfig(AppConfig):
    name = 'pretix.multidomain'
    label = 'pretixmultidomain'


default_app_config = 'pretix.multidomain.PretixMultidomainConfig'


def event_url(route, view, name=None, require_live=True):
    if callable(view):
        pattern = RegexPattern(route, name=name, is_endpoint=True)
        pattern._require_live = require_live
        return URLPattern(pattern, view, {}, name)
    raise TypeError('view must be a callable.')
