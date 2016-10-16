from django.conf import settings
from django.conf.urls import include, url

import pretix.control.urls
import pretix.presale.urls

from .base.views import cachedfiles, health, js_catalog, metrics, redirect

base_patterns = [
    url(r'^download/(?P<id>[^/]+)/$', cachedfiles.DownloadView.as_view(),
        name='cachedfile.download'),
    url(r'^healthcheck/$', health.healthcheck,
        name='healthcheck'),
    url(r'^redirect/$', redirect.redir_view, name='redirect'),
    url(r'^jsi18n/(?P<lang>[a-zA-Z-_]+)/$', js_catalog.js_catalog, name='javascript-catalog'),
    url(r'^metrics$', metrics.serve_metrics,
        name='metrics'),
]

control_patterns = [
    url(r'^control/', include((pretix.control.urls, 'control'))),
]

debug_patterns = []
if settings.DEBUG:
    try:
        import debug_toolbar

        debug_patterns.append(url(r'^__debug__/', include(debug_toolbar.urls)))
    except ImportError:
        pass

common_patterns = base_patterns + control_patterns + debug_patterns
