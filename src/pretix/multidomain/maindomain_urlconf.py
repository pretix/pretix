import importlib.util
import warnings

from django.apps import apps
from django.conf.urls import include, url
from django.views.generic import TemplateView

from pretix.presale.urls import (
    event_patterns, locale_patterns, organizer_patterns,
)
from pretix.urls import common_patterns

presale_patterns_main = [
    url(r'', include(locale_patterns + [
        url(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(event_patterns)),
        url(r'^(?P<organizer>[^/]+)/', include(organizer_patterns)),
        url(r'^$', TemplateView.as_view(template_name='pretixpresale/index.html'))
    ], namespace='presale'))
]

raw_plugin_patterns = []
for app in apps.get_app_configs():
    if hasattr(app, 'PretixPluginMeta'):
        if importlib.util.find_spec(app.name + '.urls'):
            urlmod = importlib.import_module(app.name + '.urls')
            if hasattr(urlmod, 'urlpatterns'):
                raw_plugin_patterns.append(
                    url(r'', include(urlmod, namespace=app.label))
                )
            if hasattr(urlmod, 'event_patterns'):
                raw_plugin_patterns.append(
                    url(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(urlmod.event_patterns, namespace=app.label))
                )
        elif importlib.util.find_spec(app.name + '.maindomain_urls'):
            warnings.warn('Please put your config in an \'urls\' module using the urlpatterns and event_patterns '
                          'attribute. Support for maindomain_urls in plugins will be dropped in the future.',
                          DeprecationWarning)
            urlmod = importlib.import_module(app.name + '.maindomain_urls')
            raw_plugin_patterns.append(
                url(r'', include(urlmod, namespace=app.label))
            )

plugin_patterns = [
    url(r'', include(raw_plugin_patterns, namespace='plugins'))
]

# The presale namespace comes last, because it contains a wildcard catch
urlpatterns = common_patterns + plugin_patterns + presale_patterns_main
