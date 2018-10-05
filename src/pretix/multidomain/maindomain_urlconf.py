import importlib.util
import warnings

from django.apps import apps
from django.conf.urls import include, url
from django.views.generic import TemplateView

from pretix.multidomain.plugin_handler import plugin_event_urls
from pretix.presale.urls import (
    event_patterns, locale_patterns, organizer_patterns,
)
from pretix.urls import common_patterns

presale_patterns_main = [
    url(r'', include((locale_patterns + [
        url(r'^(?P<organizer>[^/]+)/', include(organizer_patterns)),
        url(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(event_patterns)),
        url(r'^$', TemplateView.as_view(template_name='pretixpresale/index.html'), name="index")
    ], 'presale')))
]

raw_plugin_patterns = []
for app in apps.get_app_configs():
    if hasattr(app, 'PretixPluginMeta'):
        if importlib.util.find_spec(app.name + '.urls'):
            urlmod = importlib.import_module(app.name + '.urls')
            single_plugin_patterns = []
            if hasattr(urlmod, 'urlpatterns'):
                single_plugin_patterns += urlmod.urlpatterns
            if hasattr(urlmod, 'event_patterns'):
                patterns = plugin_event_urls(urlmod.event_patterns, plugin=app.name)
                single_plugin_patterns.append(url(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/',
                                                  include(patterns)))
            if hasattr(urlmod, 'organizer_patterns'):
                patterns = urlmod.organizer_patterns
                single_plugin_patterns.append(url(r'^(?P<organizer>[^/]+)/',
                                                  include(patterns)))
            raw_plugin_patterns.append(
                url(r'', include((single_plugin_patterns, app.label)))
            )
        elif importlib.util.find_spec(app.name + '.maindomain_urls'):  # noqa
            warnings.warn('Please put your config in an \'urls\' module using the urlpatterns and event_patterns '
                          'attribute. Support for maindomain_urls in plugins will be dropped in the future.',
                          DeprecationWarning)
            urlmod = importlib.import_module(app.name + '.maindomain_urls')
            raw_plugin_patterns.append(
                url(r'', include((urlmod, app.label)))
            )

plugin_patterns = [
    url(r'', include((raw_plugin_patterns, 'plugins')))
]

# The presale namespace comes last, because it contains a wildcard catch
urlpatterns = common_patterns + plugin_patterns + presale_patterns_main

handler404 = 'pretix.base.views.errors.page_not_found'
handler500 = 'pretix.base.views.errors.server_error'
