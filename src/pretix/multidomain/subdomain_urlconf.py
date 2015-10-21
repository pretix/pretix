from django.conf.urls import include, url

from pretix.presale.urls import event_patterns, locale_patterns
from pretix.urls import common_patterns

print(event_patterns)
presale_patterns = [
    url(r'', include(locale_patterns + [
        url(r'^(?P<event>[^/]+)/', include(event_patterns))
    ], namespace='presale'))
]

# The presale namespace comes last, because it contains a wildcard catch
urlpatterns = common_patterns + presale_patterns
