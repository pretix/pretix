from django.conf.urls import include, url

from .views import webhook

urlpatterns = [
    url(r'^stripe/', include([
        url(r'^webhook/$', webhook, name='webhook'),
    ])),
]

event_patterns = [
    url(r'^stripe/', include([
        url(r'^webhook/$', webhook, name='webhook'),
    ])),
]
