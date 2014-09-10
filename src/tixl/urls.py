from django.conf.urls import patterns, include, url
from django.contrib import admin

import tixlcontrol.urls


urlpatterns = patterns('',
    url(r'^control/', include(tixlcontrol.urls, namespace='control')),
    url(r'^admin/', include(admin.site.urls)),
)
