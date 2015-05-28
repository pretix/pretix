import importlib
from django.apps import apps
from django.conf.urls import include, url
from django.conf import settings

import pretix.control.urls
import pretix.presale.urls


urlpatterns = [
    url(r'^control/', include(pretix.control.urls, namespace='control')),
    # The pretixpresale namespace is configured at the bottom of this file, because it
    # contains a wildcard-style URL which has to be configured _after_ debug settings.
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns.append(
        url(r'^__debug__/', include(debug_toolbar.urls)),
    )

pluginpatterns = []
for app in apps.get_app_configs():
    if hasattr(app, 'PretixPluginMeta'):
        try:
            urlmod = importlib.import_module(app.name + '.urls')
            pluginpatterns.append(
                url(r'', include(urlmod, namespace=app.label))
            )
        except ImportError:
            pass
urlpatterns.append(
    url(r'', include(pluginpatterns, namespace='plugins'))
)

urlpatterns.append(
    url(r'', include(pretix.presale.urls, namespace='presale'))
)
