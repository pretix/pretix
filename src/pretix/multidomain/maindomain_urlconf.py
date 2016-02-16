import importlib
import importlib.util

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
        if importlib.util.find_spec(app.name + '.maindomain_urls'):
            urlmod = importlib.import_module(app.name + '.maindomain_urls')
            raw_plugin_patterns.append(
                url(r'', include(urlmod, namespace=app.label))
            )

plugin_patterns = [
    url(r'', include(raw_plugin_patterns, namespace='plugins'))
]

# The presale namespace comes last, because it contains a wildcard catch
urlpatterns = common_patterns + plugin_patterns + presale_patterns_main
