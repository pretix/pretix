from django.conf.urls import include, url

from .views import ReturnView, refund, webhook

event_patterns = [
    url(r'^stripe/', include([
        url(r'^webhook/$', webhook, name='webhook'),
        url(r'^return/(?P<order>[^/]+)/(?P<hash>[^/]+)/$', ReturnView.as_view(), name='return'),
    ])),
]

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/stripe/refund/(?P<id>\d+)/',
        refund, name='refund'),
]
