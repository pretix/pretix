from django.conf.urls import include, url

from .views import abort, event_webbook, refund, success, webhook

event_patterns = [
    url(r'^paypal/', include([
        url(r'^abort/$', abort, name='abort'),
        url(r'^return/$', success, name='return'),
        url(r'^webhook/$', event_webbook, name='webhook'),
    ])),
]


urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/paypal/refund/(?P<id>\d+)/',
        refund, name='refund'),
    url(r'^_paypal/webhook/$', webhook, name='webhook'),
]
