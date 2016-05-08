import uuid

from django.conf import settings
from django.conf.urls import include, url
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.views.decorators.http import etag
from django.views.i18n import javascript_catalog

import pretix.control.urls
import pretix.presale.urls

from .base.views import cachedfiles

# This is not a valid Django URL configuration, as the final
# configuration is done by the pretix.multidomain package.
js_info_dict = {
    'packages': ('pretix',),
}

# Yes, we want to regenerate this every time the module has been imported to
# refresh the cache at least at every code deployment
import_date = timezone.now().strftime("%Y%m%d%H%M")

base_patterns = [
    url(r'^download/(?P<id>[^/]+)/$', cachedfiles.DownloadView.as_view(),
        name='cachedfile.download'),
    url(r'^jsi18n/$',
        etag(lambda *s, **k: import_date)(cache_page(3600, key_prefix='js18n-%s' % import_date)(javascript_catalog)),
        js_info_dict, name='javascript-catalog'),
]

control_patterns = [
    url(r'^control/', include(pretix.control.urls, namespace='control')),
]

debug_patterns = []
if settings.DEBUG:
    try:
        import debug_toolbar

        debug_patterns.append(url(r'^__debug__/', include(debug_toolbar.urls)))
    except ImportError:
        pass

common_patterns = base_patterns + control_patterns + debug_patterns
