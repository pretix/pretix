from django.conf import settings
from django.conf.urls import include, url
from django.views.generic import RedirectView

import pretix.control.urls
import pretix.presale.urls

from .base.views import cachedfiles, csp, health, js_catalog, metrics, redirect

base_patterns = [
    url(r'^download/(?P<id>[^/]+)/$', cachedfiles.DownloadView.as_view(),
        name='cachedfile.download'),
    url(r'^healthcheck/$', health.healthcheck,
        name='healthcheck'),
    url(r'^redirect/$', redirect.redir_view, name='redirect'),
    url(r'^jsi18n/(?P<lang>[a-zA-Z-_]+)/$', js_catalog.js_catalog, name='javascript-catalog'),
    url(r'^metrics$', metrics.serve_metrics,
        name='metrics'),
    url(r'^csp_report/$', csp.csp_report, name='csp.report'),
    url(r'^api/v1/', include('pretix.api.urls', namespace='api-v1')),
    url(r'^api/$', RedirectView.as_view(url='/api/v1/'), name='redirect-api-version')
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
