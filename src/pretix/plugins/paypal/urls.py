from django.conf.urls import include, url

from pretix.multidomain import event_url

from .views import abort, redirect_view, refund, success, webhook

event_patterns = [
    url(r'^paypal/', include([
        url(r'^abort/$', abort, name='abort'),
        url(r'^return/$', success, name='return'),
        url(r'^redirect/$', redirect_view, name='redirect'),

        url(r'w/(?P<cart_namespace>[a-zA-Z0-9]{16})/abort/', abort, name='abort'),
        url(r'w/(?P<cart_namespace>[a-zA-Z0-9]{16})/return/', success, name='return'),

        event_url(r'^webhook/$', webhook, name='webhook', require_live=False),
    ])),
]


urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/paypal/refund/(?P<id>\d+)/',
        refund, name='refund'),
    url(r'^_paypal/webhook/$', webhook, name='webhook'),
]
