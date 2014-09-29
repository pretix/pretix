from django.conf.urls import patterns, include, url
from django.contrib import admin
from django.conf import settings

import tixlcontrol.urls


urlpatterns = patterns('',
    url(r'^control/', include(tixlcontrol.urls, namespace='control')),
    url(r'^admin/', include(admin.site.urls)),
)

if settings.DEBUG:
    urlpatterns += patterns('django.contrib.staticfiles.views',
        url(r'^static/(?P<path>.*)$', 'serve'),
    )

    import debug_toolbar
    urlpatterns += patterns('',
        url(r'^__debug__/', include(debug_toolbar.urls)),
    )
