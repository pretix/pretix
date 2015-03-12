from django.conf.urls import include, url
from django.contrib import admin
from django.conf import settings

import pretix.control.urls
import pretix.presale.urls


urlpatterns = [
    url(r'^control/', include(pretix.control.urls, namespace='control')),
    url(r'^admin/', include(admin.site.urls)),
    # The pretixpresale namespace is configured at the bottom of this file, because it
    # contains a wildcard-style URL which has to be configured _after_ debug settings.
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns.append(
        url(r'^__debug__/', include(debug_toolbar.urls)),
    )

urlpatterns.append(
    url(r'', include(pretix.presale.urls, namespace='presale'))
)
