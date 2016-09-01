from django.conf.urls import include, url

from .views import webhook

event_patterns = [
    url(r'^stripe/', include([
        url(r'^webhook/$', webhook, name='webhook'),
    ])),
]
