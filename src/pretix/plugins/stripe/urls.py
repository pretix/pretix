from django.conf.urls import include, url

from pretix.multidomain import event_url

from .views import (
    ReturnView, oauth_disconnect, oauth_return, redirect_view, refund, webhook,
)

event_patterns = [
    url(r'^stripe/', include([
        event_url(r'^webhook/$', webhook, name='webhook', require_live=False),
        url(r'^redirect/$', redirect_view, name='redirect'),
        url(r'^return/(?P<order>[^/]+)/(?P<hash>[^/]+)/$', ReturnView.as_view(), name='return'),
    ])),
]

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/stripe/refund/(?P<id>\d+)/',
        refund, name='refund'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/stripe/disconnect/',
        oauth_disconnect, name='oauth.disconnect'),
    url(r'^_stripe/webhook/$', webhook, name='webhook'),
    url(r'^_stripe/oauth_return/$', oauth_return, name='oauth.return'),
]
