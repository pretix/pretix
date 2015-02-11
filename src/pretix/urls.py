from django.conf.urls import patterns, include, url
from django.contrib import admin
from django.conf import settings

import pretixcontrol.urls
import pretixpresale.urls


urlpatterns = patterns('',
    url(r'^control/', include(pretixcontrol.urls, namespace='control')),
    url(r'^admin/', include(admin.site.urls)),
    # The pretixpresale namespace is configured at the bottom of this file, because it
    # contains a wildcard-style URL which has to be configured _after_ debug settings.
)

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += patterns('',
        url(r'^__debug__/', include(debug_toolbar.urls)),
    )

urlpatterns += patterns('',
    url(r'', include(pretixpresale.urls, namespace='presale'))
)
