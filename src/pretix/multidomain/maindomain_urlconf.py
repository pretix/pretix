from django.conf.urls import include, url

from pretix.presale.urls import (
    event_patterns, locale_patterns, organizer_patterns,
)
from pretix.urls import common_patterns

presale_patterns_main = [
    url(r'', include(locale_patterns + [
        url(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(event_patterns)),
        url(r'^(?P<organizer>[^/]+)/', include(organizer_patterns))
    ], namespace='presale'))
]

# The presale namespace comes last, because it contains a wildcard catch
urlpatterns = common_patterns + presale_patterns_main
