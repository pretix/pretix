from django.conf.urls import include, url

from pretix.multidomain import event_url

from .views import ReturnView, refund, webhook

event_patterns = [
    url(r'^stripe/', include([
        event_url(r'^webhook/$', webhook, name='webhook', require_live=False),
        url(r'^return/(?P<order>[^/]+)/(?P<hash>[^/]+)/$', ReturnView.as_view(), name='return'),
    ])),
]

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/stripe/refund/(?P<id>\d+)/',
        refund, name='refund'),
    url(r'^_stripe/webhook/$', webhook, name='webhook'),
]
