from django.conf.urls import include, url

from .views import refund, webhook

event_patterns = [
    url(r'^stripe/', include([
        url(r'^webhook/$', webhook, name='webhook'),
    ])),
]

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/stripe/refund/(?P<id>\d+)/',
        refund, name='refund'),
]
