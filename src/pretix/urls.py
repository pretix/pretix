from django.conf import settings
from django.conf.urls import include, url

import pretix.base.views.cachedfiles
import pretix.control.urls
import pretix.presale.urls

# This is not a valid Django URL configuration, as the final
# configuration is done by the pretix.multidomain package.

base_patterns = [
    url(r'^download/(?P<id>[^/]+)/$', pretix.base.views.cachedfiles.DownloadView.as_view(),
        name='cachedfile.download')
]

control_patterns = [
    url(r'^control/', include(pretix.control.urls, namespace='control')),
]

debug_patterns = []
if settings.DEBUG:
    import debug_toolbar

    debug_patterns.append(url(r'^__debug__/', include(debug_toolbar.urls)))

common_patterns = base_patterns + control_patterns + debug_patterns
